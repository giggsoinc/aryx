"""Groundedness engine — turn retrieved evidence into a verifiable record.

Every Ask answer is checked against the entities that fed it: which named
entities the answer actually references, what source records back each one, and
how much of the retrieved evidence the answer used. This is the substrate the
Accuracy Lab needs to prove an answer is grounded — not asserted — and the
signal that exposes a hallucinated entity (one named in the answer but absent
from the grounding).

Deterministic by design: no extra LLM call, so it is cheap enough to run on
every answer and cannot itself hallucinate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from aryx.ask.evidence import RetrievedEntity


@dataclass
class Citation:
    """A source record backing one entity the answer references."""

    marker: int
    entity_id: int
    entity_name: str
    entity_type: str
    system: str
    dataset: str
    record_id: str


@dataclass
class Grounding:
    """Verifiable provenance for one answer."""

    grounded: bool
    entity_count: int          # entities retrieved as evidence
    cited_count: int           # of those, how many the answer references
    source_count: int          # distinct source records behind the citations
    score: float               # cited / retrieved — evidence actually used
    citations: list[Citation] = field(default_factory=list)
    uncited_entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON-serializable form for the API / Lab UI."""
        d = asdict(self)
        d["score"] = round(self.score, 3)
        return d


def _mentions(answer: str, name: str) -> bool:
    """True if a non-trivial entity name appears in the answer (case-insensitive)."""
    name = (name or "").strip()
    if len(name) < 2:
        return False
    return name.lower() in answer.lower()


def build_grounding(answer: str, entities: list[RetrievedEntity]) -> Grounding:
    """Verify an answer against the structured evidence that produced it.

    An entity counts as *cited* when its name appears in the answer; each cited
    entity contributes its source records as numbered citations. Retrieved
    entities the answer ignores are reported as ``uncited_entities`` so the Lab
    can show evidence-coverage, not just a yes/no.
    """
    citations: list[Citation] = []
    uncited: list[str] = []
    cited_ids: set[int] = set()
    sources: set[tuple[str, str, str]] = set()
    marker = 0

    for ent in entities:
        if not _mentions(answer, ent.name):
            uncited.append(ent.name)
            continue
        cited_ids.add(ent.id)
        for src in ent.sources:
            key = (src.get("system", ""), src.get("dataset", ""),
                   str(src.get("record_id", "")))
            sources.add(key)
            marker += 1
            citations.append(Citation(
                marker=marker, entity_id=ent.id, entity_name=ent.name,
                entity_type=ent.type, system=key[0], dataset=key[1],
                record_id=key[2]))

    entity_count = len(entities)
    cited_count = len(cited_ids)
    score = (cited_count / entity_count) if entity_count else 0.0
    return Grounding(
        grounded=cited_count > 0,
        entity_count=entity_count,
        cited_count=cited_count,
        source_count=len(sources),
        score=score,
        citations=citations,
        uncited_entities=uncited,
    )
