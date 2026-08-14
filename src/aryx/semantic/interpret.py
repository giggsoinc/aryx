"""Deterministic-first semantic interpretation (C04).

Mirrors the component Procedure:
  1. select only columns relevant to the objective (candidate_columns)
  2. retrieve approved terminology (ontology types + attributes = the vocabulary)
  3. propose schema-bound candidates (lexical + optional local embeddings)
  4. require evidence references to source columns and ontology terms
  5. reject invented columns / unsupported meanings (only real columns + real
     ontology terms can appear)
  6. apply a confidence threshold and conflict rules
  7. (caller) persist accepted + unresolved annotations separately

Grounding guarantees: a column can only map to a term that exists in the
ontology, and only when the combined score clears the threshold — otherwise it
is left UNRESOLVED. No invented concepts, no guessing.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from aryx.profiler.models import DatasetProfile
from aryx.semantic.models import (
    AlternativeMapping,
    SemanticAnnotation,
    SemanticProfile,
    UnresolvedField,
)

DEFAULT_THRESHOLD = 0.6
_ALT_FLOOR = 0.45          # keep runner-ups at/above this as alternatives
_NOISE_TOKENS = {"field", "fields", "model", "pk"}


@dataclass
class Term:
    """One entry in the approved vocabulary (an ontology type or attribute)."""

    concept: str
    ontology_type: str = ""
    ontology_attribute: str = ""
    text: str = ""
    tokens: frozenset[str] = field(default_factory=frozenset)


def _tokens(name: str) -> frozenset[str]:
    """Normalize a name to a token set: split camelCase/underscores, singularize."""
    name = re.sub(r"^fields\.", "", name or "")
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    out: set[str] = set()
    for tok in re.split(r"[^A-Za-z0-9]+", name.lower()):
        if not tok or tok in _NOISE_TOKENS:
            continue
        if len(tok) > 3 and tok.endswith("s"):
            tok = tok[:-1]
        out.add(tok)
    return frozenset(out)


def make_terms(ontology: list[tuple[str, list[str]]]) -> list[Term]:
    """Build the vocabulary from (type_name, attributes) pairs.

    One term per attribute (concept = attribute, scoped by type) plus one per
    type name. Duplicate (concept, type) pairs are collapsed.
    """
    terms: list[Term] = []
    seen: set[tuple[str, str]] = set()
    for type_name, attrs in ontology:
        key = (type_name, "")
        if key not in seen:
            seen.add(key)
            terms.append(Term(concept=type_name, ontology_type=type_name,
                              text=type_name, tokens=_tokens(type_name)))
        for attr in attrs:
            concept = re.sub(r"^fields\.", "", attr)
            k = (concept, type_name)
            if k in seen:
                continue
            seen.add(k)
            terms.append(Term(concept=concept, ontology_type=type_name,
                              ontology_attribute=attr,
                              text=f"{concept} {type_name}",
                              tokens=_tokens(attr)))
    return terms


def _lexical(col_tokens: frozenset[str], term_tokens: frozenset[str]) -> float:
    """Token-set similarity: max(Jaccard, containment)."""
    if not col_tokens or not term_tokens:
        return 0.0
    inter = col_tokens & term_tokens
    if not inter:
        return 0.0
    jaccard = len(inter) / len(col_tokens | term_tokens)
    containment = len(inter) / min(len(col_tokens), len(term_tokens))
    return max(jaccard, 0.9 * containment)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def column_text(name: str) -> str:
    """The string embedded for a column (kept in sync with run.py)."""
    return re.sub(r"^fields\.", "", name or "").replace("_", " ")


def _score(col_name: str, col_tokens: frozenset[str], term: Term,
           vectors: dict[str, list[float]] | None) -> float:
    lex = _lexical(col_tokens, term.tokens)
    if lex >= 0.999:
        return 1.0
    if vectors is not None:
        cv = vectors.get(column_text(col_name))
        tv = vectors.get(term.text)
        if cv and tv:
            cos = max(0.0, _cosine(cv, tv))
            # Embeddings may only RAISE a match, never demote a strong lexical
            # one below threshold (a noisy cosine must not un-resolve a column
            # that lexical alone already grounded).
            return round(max(lex, 0.5 * lex + 0.5 * cos), 4)
    return round(lex, 4)


def interpret(
    profile: DatasetProfile,
    terms: list[Term],
    *,
    domain: str = "",
    candidate_columns: list[str] | None = None,
    vectors: dict[str, list[float]] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> SemanticProfile:
    """Map columns to grounded business concepts; leave uncertain ones unresolved.

    Args:
        profile: The C03 dataset profile (authoritative real columns).
        terms: Approved vocabulary from the ontology.
        candidate_columns: Restrict to these columns (default: all profile columns).
        vectors: Optional precomputed embeddings keyed by text; enables the
            embedding blend. None → lexical only.
        threshold: Minimum combined score to accept a mapping.
    """
    real_columns = {c.name for c in profile.columns}
    wanted = candidate_columns if candidate_columns is not None else [c.name for c in profile.columns]

    warnings: list[str] = []
    # Step 1 ranking pass — best + alternatives per column.
    ranked: list[tuple[str, list[tuple[Term, float]]]] = []
    for col in wanted:
        if col not in real_columns:          # step 5 — reject invented columns
            warnings.append(f"column {col!r} is not in the dataset profile; skipped")
            continue
        col_tokens = _tokens(col)
        scores = sorted(
            ((t, _score(col, col_tokens, t, vectors)) for t in terms),
            key=lambda ts: -ts[1],
        )
        ranked.append((col, scores))

    # Step 6 — conflict rule: each concept is claimed by its highest-confidence
    # column; a displaced column falls back to its next term above threshold.
    claimed: dict[str, str] = {}     # concept -> owning column
    order = sorted(ranked, key=lambda rc: -(rc[1][0][1] if rc[1] else 0.0))
    annotations: list[SemanticAnnotation] = []
    unresolved: list[UnresolvedField] = []

    for col, scores in order:
        chosen = None
        for term, sc in scores:
            if sc < threshold:
                break
            if term.concept in claimed:
                continue
            chosen = (term, sc)
            break
        if chosen is None:
            best = scores[0][1] if scores else 0.0
            reason = ("no ontology concept above confidence threshold"
                      if best < threshold else "best concept already claimed by a stronger column")
            unresolved.append(UnresolvedField(column=col, reason=reason,
                                              best_confidence=round(best, 4)))
            continue
        term, sc = chosen
        claimed[term.concept] = col
        alts = [
            AlternativeMapping(business_concept=t.concept, confidence=round(s, 4))
            for t, s in scores[1:4] if s >= _ALT_FLOOR and t.concept != term.concept
        ]
        evidence = "exact/lexical match" if sc >= 0.999 or vectors is None else "lexical + embedding"
        annotations.append(SemanticAnnotation(
            column=col, business_concept=term.concept, confidence=round(sc, 4),
            ontology_type=term.ontology_type, ontology_attribute=term.ontology_attribute,
            evidence=evidence, alternatives=alts,
        ))

    annotations.sort(key=lambda a: a.column)
    unresolved.sort(key=lambda u: u.column)
    if not terms:
        warnings.append("empty ontology vocabulary — nothing to ground against; "
                        "run ingestion so ontology types exist")
    return SemanticProfile(
        semantic_profile_id=f"semantic_{profile.dataset_id}_{profile.dataset_version}",
        dataset_id=profile.dataset_id, dataset_version=profile.dataset_version,
        dataset_profile_ref=profile.dataset_profile_id, domain=domain,
        annotations=annotations, unresolved_fields=unresolved, warnings=warnings,
        profile_status="valid",
    )
