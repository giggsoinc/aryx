"""Ask overview: cost per question, privacy of record fields, fallbacks.

Covers the review findings on the exact-counts change:

* M1 — the overview is built from ONE set of queries per request, cached per
  workspace, and sample names come from one query instead of one per type;
* M2 — ``ARYX_ASK_ATTRIBUTES`` (off / safe / all) controls what record field
  values reach the answer model;
* L1 — breakdown keys are ranked (``status`` first), not alphabetical;
* L2 — the header says "exact" only when the counts are exact;
* L3 — a fallback is logged once per adapter, with the workspace id;
* N1/N2 — prompt wording about partial coverage.

Pure logic with fake readers — no database, no LLM.
"""
from __future__ import annotations

import types
from typing import Any

import pytest

from aryx import llm_runtime
from aryx.api import ask_api, ask_overview
from aryx.ask.evidence import RetrievedEntity
from aryx.graph import ask_facts, overview_cache
from aryx.graph.ask_facts import (
    entity_attributes, format_breakdown, is_sensitive_key, type_counts,
)
from aryx.graph.retrieve import all_types


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """No DB lookups, a clean cache, and a clean once-per-adapter log memory."""
    overview_cache.invalidate()
    ask_facts._logged.clear()
    monkeypatch.setattr(ask_overview, "_relationships", lambda ws: [])
    monkeypatch.setattr(ask_overview, "_aim", lambda ws: [])
    monkeypatch.setattr(ask_overview, "_ttl", lambda: 60)
    monkeypatch.setattr(ask_facts, "attributes_mode", lambda: "safe")
    yield
    overview_cache.invalidate()


class _Reader:
    """Postgres-reader shaped fake that counts how often each query runs."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}
        self.entities = [
            {"id": 1, "type": "Ticket", "name": "TKT-1"},
            {"id": 2, "type": "Contract", "name": "CT-1"},
        ]

    def _hit(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def count_by_type(self) -> dict[str, int]:
        self._hit("count_by_type")
        return {"Contract": 600, "Ticket": 160}

    def attribute_breakdown(self, max_values: int = 8) -> dict[str, dict[str, dict[str, int]]]:
        self._hit("attribute_breakdown")
        return {"Ticket": {"status": {"open": 54, "closed": 106}}}

    def sample_names(self, per_type: int = 3) -> dict[str, list[str]]:
        self._hit("sample_names")
        return {"Contract": ["CT-1", "CT-2", "CT-3"], "Ticket": ["TKT-1", "TKT-2"]}

    def find_entities(self, ontology_type: str | None = None,
                      name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self._hit("find_entities")
        return [e for e in self.entities if not ontology_type or e["type"] == ontology_type]


class _OldAdapter:
    """An adapter from before the Ask methods existed: only ``find_entities``."""

    def find_entities(self, ontology_type: str | None = None,
                      name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return [{"id": 1, "type": "Ticket", "name": "TKT-1"}][:limit]


# --- M1: cost per question -------------------------------------------------

def test_one_request_counts_types_once_and_returns_the_types() -> None:
    reader = _Reader()
    text, types = ask_overview.build_with_types(reader, 1)
    assert types == ["Contract", "Ticket"]
    assert reader.calls["count_by_type"] == 1          # not once for types + once for text
    assert reader.calls["sample_names"] == 1           # one query, not one per type
    assert "find_entities" not in reader.calls
    assert "- Contract: 600 records" in text


def test_second_question_is_served_from_the_cache() -> None:
    reader = _Reader()
    first = ask_overview.build_with_types(reader, 1)
    second = ask_overview.build_with_types(reader, 1)
    assert second == first
    assert reader.calls["count_by_type"] == 1
    assert reader.calls["attribute_breakdown"] == 1


def test_cache_is_per_workspace() -> None:
    reader = _Reader()
    ask_overview.build_with_types(reader, 1)
    ask_overview.build_with_types(reader, 2)
    assert reader.calls["count_by_type"] == 2


def test_invalidate_forces_a_rebuild() -> None:
    """What ``after_graph_change`` does after an ingest, merge or correction."""
    reader = _Reader()
    ask_overview.build_with_types(reader, 1)
    overview_cache.invalidate(1)
    ask_overview.build_with_types(reader, 1)
    assert reader.calls["count_by_type"] == 2


def test_ttl_zero_disables_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_overview, "_ttl", lambda: 0)
    reader = _Reader()
    ask_overview.build_with_types(reader, 1)
    ask_overview.build_with_types(reader, 1)
    assert reader.calls["count_by_type"] == 2


def test_expired_entry_is_rebuilt(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    clock = types.SimpleNamespace(monotonic=lambda: now[0])
    monkeypatch.setattr(overview_cache, "time", clock)      # only this module's clock
    reader = _Reader()
    ask_overview.build_with_types(reader, 1)
    now[0] += 61                                        # past the 60 s TTL
    ask_overview.build_with_types(reader, 1)
    assert reader.calls["count_by_type"] == 2


def test_a_degraded_overview_is_never_cached() -> None:
    class _Down(_Reader):
        def count_by_type(self) -> dict[str, int]:
            raise RuntimeError("db down")

        def find_entities(self, ontology_type=None, name=None, limit=50):  # noqa: ANN001, ANN201
            raise RuntimeError("db down")

    reader = _Down()
    text, types = ask_overview.build_with_types(reader, 1)
    assert types == [] and "Kinds tracked" not in text
    assert overview_cache.get(1, 60) is None


def test_sample_names_fall_back_to_one_query_per_type_when_the_adapter_lacks_it() -> None:
    names = ask_facts.sample_names(_OldAdapter(), ["Ticket"])
    assert names == {"Ticket": ["TKT-1"]}


def test_sample_names_fall_back_when_the_single_query_fails() -> None:
    class _Broken(_Reader):
        def sample_names(self, per_type: int = 3) -> dict[str, list[str]]:
            raise RuntimeError("boom")

    names = ask_facts.sample_names(_Broken(), ["Ticket", "Contract"])
    assert names == {"Ticket": ["TKT-1"], "Contract": ["CT-1"]}


# --- L2: the header tells the truth about exactness -------------------------

def test_header_says_exact_only_when_counts_are_exact() -> None:
    text, _ = ask_overview.build_with_types(_Reader(), 1)
    assert text.startswith("WORKSPACE OVERVIEW (counts are exact totals")


def test_header_says_approximate_in_fallback_mode() -> None:
    text, _ = ask_overview.build_with_types(_OldAdapter(), 1)
    assert "approximate" in text.splitlines()[0]
    assert "exact totals" not in text
    assert "at least 1 records" in text


def test_prompt_matches_the_header_and_explains_partial_coverage(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_chat(role: str, system: str, user: str) -> tuple[str, int, int]:
        seen["prompt"] = user
        return "ok", 1, 1

    monkeypatch.setattr(llm_runtime, "chat", fake_chat)
    ask_api._synthesise("How many?", "", "WORKSPACE OVERVIEW:")
    prompt = seen["prompt"]
    assert "exact, unless a line says 'at least'" in prompt        # L2
    assert "may not add up to the type's total" in prompt           # N2
    assert "exact totals counted from the database" not in prompt


# --- L3: log a fallback once, with the workspace ---------------------------

class _Recorder:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, level: str, message: str, **kw: Any) -> None:
        self.records.append((kw.get("error_code", ""), kw.get("context", {})))


def test_a_missing_method_is_logged_once_per_adapter_not_per_question(
        monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recorder()
    monkeypatch.setattr(ask_facts, "raven_log", rec)
    for _ in range(5):
        type_counts(_OldAdapter(), 7)
    assert [code for code, _ in rec.records] == ["ASK_COUNTS_APPROXIMATE"]
    assert rec.records[0][1]["workspace_id"] == 7
    assert rec.records[0][1]["object_id"] == "_OldAdapter"


def test_a_different_adapter_class_is_logged_separately(
        monkeypatch: pytest.MonkeyPatch) -> None:
    class _Other(_OldAdapter):
        pass

    rec = _Recorder()
    monkeypatch.setattr(ask_facts, "raven_log", rec)
    type_counts(_OldAdapter(), 1)
    type_counts(_Other(), 1)
    assert len(rec.records) == 2


def test_all_types_passes_the_workspace_to_the_fallback_log(
        monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recorder()
    monkeypatch.setattr(ask_facts, "raven_log", rec)
    assert all_types(_OldAdapter(), 42) == ["Ticket"]
    assert rec.records[0][1]["workspace_id"] == 42


def test_an_unreadable_setting_defaults_to_safe_and_is_logged(
        monkeypatch: pytest.MonkeyPatch) -> None:
    import aryx.config

    def boom() -> Any:
        raise RuntimeError("bad env")

    monkeypatch.undo()                                   # use the real attributes_mode
    monkeypatch.setattr(aryx.config, "get_settings", boom)
    rec = _Recorder()
    monkeypatch.setattr(ask_facts, "raven_log", rec)
    assert ask_facts.attributes_mode() == "safe"
    assert rec.records[0][0] == "ASK_ATTRIBUTES_MODE_DEFAULTED"


# --- M2: what reaches the answer model -------------------------------------

class _FieldsReader:
    def entity_attributes(self, entity_ids: list[int]) -> dict[int, dict[str, Any]]:
        return {1: {"status": "open", "amount": "5000", "customer_email": "z@example.com",
                    "phone": "555-123-4567", "billing_address": "1 Main St",
                    "note": "call back", "contact": "zed@example.com",
                    "ssn": "123-45-6789", "apiKey": "abc"}}

    def attribute_breakdown(self, max_values: int = 8) -> dict[str, dict[str, dict[str, int]]]:
        return {"Customers": {"tier": {"gold": 3}, "email": {"a@b.com": 2},
                              "contact": {"x@y.org": 1, "plain": 4}}}


_ENT = [RetrievedEntity(id=1, type="Ticket", name="T")]


def test_safe_mode_drops_sensitive_keys_and_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_facts, "attributes_mode", lambda: "safe")
    attrs = entity_attributes(_FieldsReader(), _ENT)[1]
    assert attrs == {"status": "open", "amount": "5000", "note": "call back"}


def test_all_mode_sends_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_facts, "attributes_mode", lambda: "all")
    attrs = entity_attributes(_FieldsReader(), _ENT)[1]
    assert attrs["customer_email"] == "z@example.com" and attrs["ssn"] == "123-45-6789"


def test_off_mode_sends_no_field_values_at_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_facts, "attributes_mode", lambda: "off")
    assert entity_attributes(_FieldsReader(), _ENT) == {}
    assert ask_facts.attribute_breakdown(_FieldsReader()) == {}


def test_safe_breakdown_drops_sensitive_keys_and_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_facts, "attributes_mode", lambda: "safe")
    out = ask_facts.attribute_breakdown(_FieldsReader())
    assert out == {"Customers": {"tier": {"gold": 3}, "contact": {"plain": 4}}}


def test_the_overview_leaves_sensitive_breakdowns_out(monkeypatch: pytest.MonkeyPatch) -> None:
    class _R(_Reader):
        def attribute_breakdown(self, max_values: int = 8):  # noqa: ANN201
            return {"Ticket": {"status": {"open": 1, "closed": 2},
                               "email": {"a@b.com": 2, "c@d.com": 1}}}

    text, _ = ask_overview.build_with_types(_R(), 1)
    assert "status: closed 2, open 1" in text
    assert "a@b.com" not in text and "email:" not in text


@pytest.mark.parametrize("key", [
    "email", "Email", "customer_email", "customerEmail", "billing_address",
    "phone_number", "mobile", "ssn", "api_key", "apiKey", "password", "auth_token",
    "date_of_birth", "dob", "zip", "credit_card", "iban", "account_number", "salary"])
def test_sensitive_keys_are_recognised(key: str) -> None:
    assert is_sensitive_key(key)


@pytest.mark.parametrize("key", [
    "status", "priority", "amount", "tier", "city", "category", "subject",
    "ticket_id", "contract_id", "discard_reason", "cardinality", "pinned"])
def test_ordinary_keys_are_not_sensitive(key: str) -> None:
    assert not is_sensitive_key(key)


@pytest.mark.parametrize("value, sensitive", [
    ("z@example.com", True), ("555-123-4567", True), ("(555) 123 4567", True),
    ("4111 1111 1111 1111", True), ("1000", False), ("TKT-5003", False),
    ("open", False), ("2026-11-13", False), (12345, False)])
def test_sensitive_values_are_recognised(value: Any, sensitive: bool) -> None:
    assert ask_facts._is_sensitive_value(value) is sensitive


# --- L1: which breakdown keys survive the cap -------------------------------

def test_status_survives_the_key_cap_even_when_it_sorts_last() -> None:
    keys = ["category", "channel", "country", "currency", "department", "priority", "status"]
    by_attr = {k: {"a": 5, "b": 3} for k in keys}
    by_attr["status"] = {"open": 1, "closed": 1}          # carried by the FEWEST records
    shown = [line.split(":")[0] for line in format_breakdown(by_attr)]
    assert len(shown) == ask_facts.MAX_BREAKDOWN_KEYS
    assert shown[:2] == ["status", "priority"]
    assert "department" not in shown                      # alphabetical order would keep it


def test_non_preferred_keys_are_ranked_by_how_many_records_carry_them() -> None:
    by_attr = {"aaa": {"x": 1}, "zzz": {"x": 50}}
    assert [line.split(":")[0] for line in format_breakdown(by_attr)] == ["zzz", "aaa"]


# --- M1: very large workspaces skip the expensive value counts -------------

def test_a_workspace_over_the_limit_keeps_counts_but_skips_value_counts(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_facts, "breakdown_limit", lambda: 100)   # reader has 760 entities
    reader = _Reader()
    text, types_ = ask_overview.build_with_types(reader, 1)
    assert "attribute_breakdown" not in reader.calls                  # the heavy pass never ran
    assert "- Contract: 600 records" in text and "- Ticket: 160 records" in text
    assert "status:" not in text and types_ == ["Contract", "Ticket"]


def test_skipping_value_counts_is_logged_once_per_workspace(
        monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recorder()
    monkeypatch.setattr(ask_facts, "raven_log", rec)
    monkeypatch.setattr(ask_facts, "breakdown_limit", lambda: 100)
    for _ in range(4):
        ask_facts.attribute_breakdown(_Reader(), 5, 760)
    skipped = [ctx for code, ctx in rec.records if code == "ASK_BREAKDOWN_SKIPPED"]
    assert len(skipped) == 1 and skipped[0]["workspace_id"] == 5
    assert "760 entities" in skipped[0]["detail"]


def test_limit_zero_means_no_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_facts, "breakdown_limit", lambda: 0)
    reader = _Reader()
    text, _ = ask_overview.build_with_types(reader, 1)
    assert reader.calls["attribute_breakdown"] == 1 and "status: closed 106, open 54" in text


def test_a_workspace_under_the_limit_gets_value_counts(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_facts, "breakdown_limit", lambda: 10_000)
    text, _ = ask_overview.build_with_types(_Reader(), 1)
    assert "status: closed 106, open 54" in text


def test_an_unreadable_limit_setting_uses_the_default_and_is_logged(
        monkeypatch: pytest.MonkeyPatch) -> None:
    import aryx.config

    def boom() -> Any:
        raise RuntimeError("bad env")

    monkeypatch.undo()
    monkeypatch.setattr(aryx.config, "get_settings", boom)
    rec = _Recorder()
    monkeypatch.setattr(ask_facts, "raven_log", rec)
    assert ask_facts.breakdown_limit() == 50_000
    assert rec.records[0][0] == "ASK_BREAKDOWN_LIMIT_DEFAULTED"
