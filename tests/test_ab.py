"""Ontology on/off A/B tests (v2 Phase 1.2).

Pin the scorecard contract the Accuracy Lab renders: the ON variant is graded
against real evidence and the OFF variant against none, so the same model on
the same question shows grounded-with-citations vs asserted. Pure logic — the
answers are injected, no LLM.
"""
from __future__ import annotations

from aryx.ask.ab import run_ab
from aryx.ask.evidence import RetrievedEntity


def _ent(eid: int, name: str) -> RetrievedEntity:
    return RetrievedEntity(id=eid, type="Customer", name=name,
                           sources=[{"system": "sf", "dataset": "Account",
                                     "record_id": str(eid)}])


def test_on_is_grounded_off_is_not() -> None:
    evidence = [_ent(1, "Acme Corp")]
    res = run_ab("Who is Acme?", evidence,
                 answer_on="Acme Corp is a customer.",
                 answer_off="Acme Corp is probably a customer.",
                 model="local/llama")
    assert res.on.grounding.grounded is True
    assert res.off.grounding.grounded is False
    sc = res.scorecard
    assert sc["grounded"] == {"on": True, "off": False}
    assert sc["citations"]["on"] == 1
    assert sc["citations"]["off"] == 0
    assert sc["source_records"]["on"] == 1
    assert sc["source_records"]["off"] == 0


def test_off_variant_never_cites_even_if_it_names_entities() -> None:
    """OFF is graded against no evidence, so a confident name earns no citation
    — that is exactly the ungrounded-assertion the Lab exposes."""
    evidence = [_ent(1, "Acme Corp")]
    res = run_ab("List customers", evidence,
                 answer_on="Acme Corp.",
                 answer_off="Acme Corp, Globex, and Initech.")
    assert res.off.grounding.citations == []
    assert res.off.grounded_in_ontology is False
    assert res.on.grounded_in_ontology is True


def test_to_dict_is_json_safe_and_complete() -> None:
    res = run_ab("q", [_ent(1, "Acme Corp")], "Acme Corp.", "Acme Corp.", "m")
    d = res.to_dict()
    assert set(d) == {"question", "model", "on", "off", "scorecard"}
    assert isinstance(d["on"]["grounding"]["citations"], list)
    assert d["on"]["label"] == "Ontology on"
    assert d["off"]["label"] == "Ontology off"
