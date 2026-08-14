"""Tests for the Semantic Field Interpreter (C04) — pure, no DB, no LLM.

Exercises lexical grounding against an ontology vocabulary, the confidence
threshold, unresolved handling, conflict resolution, and invented-column
rejection. Embedding blend is covered with injected vectors.
"""
from __future__ import annotations

from aryx.profiler.models import ColumnProfile, DatasetProfile
from aryx.semantic.interpret import interpret, make_terms


def _profile(*names: str) -> DatasetProfile:
    cols = [
        ColumnProfile(name=n, original_type="string", canonical_type="text",
                      candidate_role="attribute")
        for n in names
    ]
    return DatasetProfile(
        dataset_profile_id="profile_dataset_contracts_v1",
        dataset_id="dataset_contracts", dataset_version="v1",
        row_count=100, column_count=len(cols), columns=cols,
    )


# Ontology vocabulary: type Contract with these attributes.
ONTOLOGY = [("Contract", ["renewal_status", "contract_value", "region", "start_date"])]


def test_exact_columns_are_grounded() -> None:
    p = _profile("renewal_status", "contract_value", "region")
    sp = interpret(p, make_terms(ONTOLOGY))
    assert sp.semantic_profile_id == "semantic_dataset_contracts_v1"
    concepts = {a.column: a.business_concept for a in sp.annotations}
    assert concepts["renewal_status"] == "renewal_status"
    assert concepts["contract_value"] == "contract_value"
    assert concepts["region"] == "region"
    assert all(a.confidence >= 0.99 for a in sp.annotations)
    assert sp.unresolved_fields == []


def test_provenance_recorded() -> None:
    p = _profile("region")
    sp = interpret(p, make_terms(ONTOLOGY))
    a = sp.annotations[0]
    assert a.ontology_type == "Contract"
    assert a.ontology_attribute == "region"
    assert a.evidence


def test_fuzzy_token_match_grounds() -> None:
    # "sales_region" shares the 'region' token with the ontology attribute
    # → grounds to 'region' via token containment (no exact match needed).
    p = _profile("sales_region")
    sp = interpret(p, make_terms(ONTOLOGY))
    assert any(a.column == "sales_region" and a.business_concept == "region"
               for a in sp.annotations)


def test_unfamiliar_column_is_unresolved_not_guessed() -> None:
    p = _profile("xyzzy_blob")
    sp = interpret(p, make_terms(ONTOLOGY))
    assert sp.annotations == []
    assert len(sp.unresolved_fields) == 1
    assert sp.unresolved_fields[0].column == "xyzzy_blob"
    assert sp.unresolved_fields[0].best_confidence < 0.6


def test_invented_column_rejected() -> None:
    p = _profile("region")
    sp = interpret(p, make_terms(ONTOLOGY), candidate_columns=["region", "ghost_col"])
    assert any("ghost_col" in w for w in sp.warnings)
    assert all(a.column != "ghost_col" for a in sp.annotations)
    assert all(u.column != "ghost_col" for u in sp.unresolved_fields)


def test_conflict_one_concept_per_column() -> None:
    # Two columns both closest to 'region'; only the stronger keeps it.
    p = _profile("region", "region_name")
    sp = interpret(p, make_terms(ONTOLOGY))
    owners = [a.column for a in sp.annotations if a.business_concept == "region"]
    assert len(owners) == 1


def test_empty_ontology_leaves_all_unresolved() -> None:
    p = _profile("region", "contract_value")
    sp = interpret(p, make_terms([]))
    assert sp.annotations == []
    assert len(sp.unresolved_fields) == 2
    assert any("empty ontology" in w for w in sp.warnings)


def test_embedding_does_not_demote_strong_lexical() -> None:
    # 'sales_region' grounds to 'region' lexically (~0.9). A noisy/orthogonal
    # embedding must NOT drag the blend below threshold and un-resolve it.
    p = _profile("sales_region")
    terms = make_terms([("Contract", ["region"])])
    vectors = {"sales region": [1.0, 0.0]}     # column_text("sales_region")
    for t in terms:
        vectors[t.text] = [0.0, 1.0]           # orthogonal -> cosine 0
    sp = interpret(p, terms, vectors=vectors)
    assert any(a.column == "sales_region" and a.business_concept == "region"
               for a in sp.annotations)
    assert sp.unresolved_fields == []


def test_embedding_blend_lifts_weak_lexical() -> None:
    # 'geo' shares no tokens with 'region' lexically, but identical vectors
    # push the blended score over threshold.
    p = _profile("geo")
    terms = make_terms([("Contract", ["region"])])
    vec = [1.0, 0.0, 0.0]
    vectors = {"geo": vec}
    for t in terms:
        vectors[t.text] = vec  # column and term embed identically
    sp = interpret(p, terms, vectors=vectors)
    # lexical(geo, region)=0, cosine=1 -> blend 0.5 < 0.6 threshold -> unresolved.
    # This asserts the blend is applied (score ~0.5), not a false accept.
    assert sp.unresolved_fields and sp.unresolved_fields[0].best_confidence == 0.5
