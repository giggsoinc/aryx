"""Groundedness-engine tests (v2 Phase 1).

These pin the contract the Accuracy Lab depends on: an answer is graded
against the evidence that produced it — cited entities earn citations from
their sources, ignored evidence is reported, and an empty retrieval is honestly
ungrounded. No graph, no LLM — pure verification logic.
"""
from __future__ import annotations

from aryx.ask.evidence import RetrievedEntity
from aryx.ask.grounding import build_grounding


def _ent(eid: int, name: str, sources: list[dict] | None = None) -> RetrievedEntity:
    return RetrievedEntity(id=eid, type="Customer", name=name,
                           neighbors=[], sources=sources or [])


def test_cited_entity_earns_citations_from_its_sources() -> None:
    ents = [_ent(1, "Acme Corp", [
        {"system": "salesforce", "dataset": "Account", "record_id": "001"},
        {"system": "postgres", "dataset": "customers", "record_id": "42"},
    ])]
    g = build_grounding("Acme Corp has two open tickets.", ents)
    assert g.grounded is True
    assert g.cited_count == 1
    assert g.source_count == 2
    assert len(g.citations) == 2
    assert g.score == 1.0
    assert g.citations[0].entity_name == "Acme Corp"


def test_uncited_evidence_is_reported_and_lowers_score() -> None:
    ents = [
        _ent(1, "Acme Corp", [{"system": "sf", "dataset": "Account", "record_id": "1"}]),
        _ent(2, "Globex", [{"system": "sf", "dataset": "Account", "record_id": "2"}]),
    ]
    g = build_grounding("Acme Corp is a customer.", ents)
    assert g.cited_count == 1
    assert g.entity_count == 2
    assert g.score == 0.5
    assert g.uncited_entities == ["Globex"]


def test_no_evidence_is_honestly_ungrounded() -> None:
    g = build_grounding("Here is what the workspace tracks.", [])
    assert g.grounded is False
    assert g.entity_count == 0
    assert g.cited_count == 0
    assert g.score == 0.0
    assert g.citations == []


def test_answer_naming_an_entity_not_in_evidence_does_not_invent_citations() -> None:
    """The hallucination signal: a name in the answer with no backing entity
    earns no citation — grounding reflects only verifiable evidence."""
    ents = [_ent(1, "Acme Corp", [{"system": "sf", "dataset": "Account", "record_id": "1"}])]
    g = build_grounding("Initech and Hooli are also customers.", ents)
    assert g.grounded is False
    assert g.cited_count == 0
    assert g.citations == []
    assert g.uncited_entities == ["Acme Corp"]


def test_to_dict_is_json_safe_and_rounds_score() -> None:
    ents = [_ent(i, f"E{i}", []) for i in range(3)]
    g = build_grounding("E0 only.", ents)
    d = g.to_dict()
    assert d["score"] == round(1 / 3, 3)
    assert isinstance(d["citations"], list)
    assert set(d) == {"grounded", "entity_count", "cited_count",
                      "source_count", "score", "citations", "uncited_entities"}
