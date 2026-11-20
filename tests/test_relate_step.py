"""The Relate step keeps its job (the model judges candidate pairs) but picks
better pairs, asks several at once, and survives a failed answer."""
from __future__ import annotations

import pytest

from aryx.pipeline import enrich


class _Store:
    def __init__(self, entities, existing=()):
        self._e, self._r, self.saved = entities, list(existing), None

    def list_entities(self):
        return self._e

    def list_relationships(self):
        return self._r

    def save_relationships(self, rels):
        self.saved = rels


def _ents():
    return ([(i, "Employee", {"name": f"e{i}"}) for i in range(1, 5)]
            + [(i, "Department", {"name": f"d{i}"}) for i in range(10, 13)]
            + [(i, "Project", {"name": f"p{i}"}) for i in range(20, 23)])


def test_type_pairs_already_linked_are_not_asked_again():
    existing = [(1, 10, "IN_DEPT")]                       # Employee-Department linked
    pairs = enrich._candidate_pairs(_ents(), existing, 150)
    kinds = {frozenset((a[1], b[1])) for a, b in pairs}
    assert frozenset(("Employee", "Department")) not in kinds
    assert frozenset(("Employee", "Project")) in kinds     # still looked at
    assert all(a[0] != b[0] for a, b in pairs)


def test_pairs_are_capped_and_spread_over_type_pairs():
    pairs = enrich._candidate_pairs(_ents(), [], 6)
    assert len(pairs) == 6
    assert len({frozenset((a[1], b[1])) for a, b in pairs}) == 6   # one per type pair


def test_a_failed_pair_costs_only_that_pair(monkeypatch):
    calls = []

    def fake(left, right, _broker):
        calls.append((left["name"], right["name"]))
        if len(calls) == 1:
            raise TimeoutError("gemini timed out")
        return "related_to", 0.9

    monkeypatch.setattr(enrich, "infer_relationship", fake)
    store = _Store(_ents())
    found = enrich._relate(store, broker=None, max_pairs=8)
    assert found == len(store.saved) == len(calls) - 1     # every other pair counted


def test_time_budget_stops_the_step_but_keeps_what_was_found(monkeypatch):
    monkeypatch.setattr(enrich, "_BUDGET_S", -1)           # already over budget
    monkeypatch.setattr(enrich, "_WORKERS", 1)
    monkeypatch.setattr(enrich, "infer_relationship", lambda *_: ("x", 1.0))
    store = _Store(_ents())
    found = enrich._relate(store, broker=None, max_pairs=50)
    assert 1 <= found < 50 and store.saved is not None


def test_cloud_failure_with_no_local_model_reports_the_cloud_error(monkeypatch):
    from aryx import llm

    class Spec:
        provider, name, endpoint, api_key_ref = "google", "gemini-2.5-flash", "http://x", None

    class Broker:
        secrets = type("S", (), {"get": staticmethod(lambda _r: None)})()
        def choose(self, _t): return Spec()
        def charge(self, *_a): pass

    def cloud(*_a, **_k):
        raise RuntimeError("HTTP 503 unavailable")

    def local(*_a, **_k):
        raise OSError("Name or service not known")

    monkeypatch.setattr(llm, "openai_json", cloud)
    monkeypatch.setattr(llm, "ollama_json", local)
    with pytest.raises(RuntimeError, match="503"):          # not the Ollama DNS error
        llm.complete_json(Broker(), "frontier", "s", "u", {})
