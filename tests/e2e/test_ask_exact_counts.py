"""Ask sees exact counts and record fields on a real database.

A workspace larger than the 500-row sample the overview used to rely on:
520 contracts + 160 tickets (53 open) + 5 customers. Against real Postgres this
proves the three new reader queries and that ``POST /ask`` hands the model the
exact totals, the value breakdown, and the record's own attributes. The LLM is
stubbed — what matters here is what the model is *given*, not what it says.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aryx import llm_runtime
from aryx.api.ask_api import ask_router
from aryx.api.ask_overview import build as build_overview
from aryx.api.ask_overview import build_with_types
from aryx.graph import ask_facts, overview_cache
from aryx.graph.changes import after_graph_change
from aryx.graph.pg_reader import PostgresGraphReader
from aryx.models import Relationship, ResolvedEntity
from aryx.store.entity_store import EntityStore

pytestmark = pytest.mark.e2e

_CONTRACTS, _TICKETS, _CUSTOMERS = 520, 160, 6   # 6 customers: 5 plain + "Zed Corp"
_OPEN = len([i for i in range(_TICKETS) if i % 3 == 0])     # 54
_CLOSED = _TICKETS - _OPEN                                    # 106
_HIGH = len([i for i in range(_TICKETS) if i % 5 == 0])     # 32


@pytest.fixture(autouse=True)
def _fresh_overview_cache() -> Any:
    """The overview is cached per workspace id; start and end every test clean."""
    overview_cache.invalidate()
    yield
    overview_cache.invalidate()


@pytest.fixture
def big_workspace(e2e_dsn: str, workspace: dict[str, Any]) -> dict[str, Any]:
    """Customers first, then contracts, then tickets — so with ids ascending,
    every ticket sits beyond the first 500 entities."""
    rows: list[tuple[str, dict[str, Any]]] = []
    rows += [("Customers", {"name": f"Customer {i}", "tier": "gold"})
             for i in range(_CUSTOMERS - 1)]
    # A customer carrying personal data, for the ARYX_ASK_ATTRIBUTES checks.
    rows.append(("Customers", {"name": "Zed Corp", "tier": "gold",
                               "email": "zed@example.com", "phone": "555-123-4567"}))
    rows += [("Contract", {"name": f"CT-{2000 + i}", "amount": str(i * 100)})
             for i in range(_CONTRACTS)]
    # Ticket 0 gets a digit-free name: a term with digits is treated as an
    # entity *id* lookup, which would make this test depend on sequence values.
    # The first five tickets also carry a UNIQUE free-text "note" — a sparse key
    # that must not be mistaken for a category.
    rows += [("Ticket", {"name": "ALPHA-TICKET" if i == 0 else f"TKT-{5000 + i}",
                         "subject": "radio down",
                         "status": "open" if i % 3 == 0 else "closed",
                         "priority": "high" if i % 5 == 0 else "low",
                         **({"note": f"call back {i}"} if i < 5 else {})})
             for i in range(_TICKETS)]
    store = EntityStore(e2e_dsn, workspace["id"])
    store.save([(ResolvedEntity(ontology_type=t, attributes=a, confidence=1.0), [])
                for t, a in rows])
    ids = sorted(r[0] for r in store.list_entities())
    first_ticket = ids[_CUSTOMERS + _CONTRACTS]
    store.save_relationships([Relationship(
        source_entity_id=first_ticket, target_entity_id=ids[0],
        name="TICKET_CUSTOMERS", confidence=1.0)])
    return {"dsn": e2e_dsn, "ws": workspace["id"], "first_ticket": first_ticket}


def test_count_by_type_is_exact_beyond_500_rows(big_workspace: dict[str, Any]) -> None:
    reader = PostgresGraphReader(big_workspace["dsn"], big_workspace["ws"])
    assert reader.count_by_type() == {
        "Contract": _CONTRACTS, "Customers": _CUSTOMERS, "Ticket": _TICKETS}
    # The old path really was capped — this is the bug being fixed.
    assert len(reader.find_entities(limit=10_000)) == 500


def test_attribute_breakdown_counts_categories_and_skips_identifiers(
        big_workspace: dict[str, Any]) -> None:
    reader = PostgresGraphReader(big_workspace["dsn"], big_workspace["ws"])
    breakdown = reader.attribute_breakdown()
    assert breakdown["Ticket"]["status"] == {"open": _OPEN, "closed": _CLOSED}
    assert breakdown["Ticket"]["priority"]["high"] == _HIGH
    assert "name" not in breakdown["Ticket"]       # unique per record
    assert "name" not in breakdown.get("Contract", {})
    assert "amount" not in breakdown.get("Contract", {})


def test_entity_attributes_returns_the_record_fields(big_workspace: dict[str, Any]) -> None:
    reader = PostgresGraphReader(big_workspace["dsn"], big_workspace["ws"])
    tid = big_workspace["first_ticket"]
    attrs = reader.entity_attributes([tid, -1])
    assert attrs[tid]["status"] == "open"
    assert attrs[tid]["priority"] == "high"
    assert -1 not in attrs
    assert reader.entity_attributes([]) == {}


def test_overview_has_the_real_totals_and_breakdown(big_workspace: dict[str, Any]) -> None:
    reader = PostgresGraphReader(big_workspace["dsn"], big_workspace["ws"])
    text = build_overview(reader, big_workspace["ws"])
    assert f"- Contract: {_CONTRACTS} records" in text
    assert f"- Ticket: {_TICKETS} records" in text       # was missing entirely
    assert f"status: closed {_CLOSED}, open {_OPEN}" in text


def test_ask_gives_the_model_totals_attributes_and_link_counts(
        big_workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_chat(role: str, system: str, user: str) -> tuple[str, int, int]:
        if role == "menial":
            return '{"terms": ["ALPHA-TICKET"]}', 1, 1
        seen["prompt"] = user
        return "It is open.", 1, 1

    monkeypatch.setattr(llm_runtime, "chat", fake_chat)
    app = FastAPI()
    app.include_router(ask_router())
    body = TestClient(app).post("/ask", json={
        "question": "What is the status of the alpha ticket?",
        "workspace_id": big_workspace["ws"]}).json()

    assert body["answer"] == "It is open."
    prompt = seen["prompt"]
    assert f"- Ticket: {_TICKETS} records" in prompt            # exact total
    assert f"status: closed {_CLOSED}, open {_OPEN}" in prompt  # breakdown
    assert "ALPHA-TICKET [Ticket]" in prompt                    # the record
    assert "status=open" in prompt                              # its field
    assert "1 x Customers (-> TICKET_CUSTOMERS)" in prompt      # link total


# --- review follow-ups: sparse keys, one-query samples, cache, privacy -----------

def test_a_sparse_free_text_key_is_not_a_category(big_workspace: dict[str, Any]) -> None:
    """5 unique notes on 5 of 160 tickets: distinct values == records WITH the key."""
    reader = PostgresGraphReader(big_workspace["dsn"], big_workspace["ws"])
    breakdown = reader.attribute_breakdown()
    assert "note" not in breakdown["Ticket"]
    assert "status" in breakdown["Ticket"]


def test_sample_names_come_from_one_query_in_id_order(big_workspace: dict[str, Any]) -> None:
    reader = PostgresGraphReader(big_workspace["dsn"], big_workspace["ws"])
    names = reader.sample_names(3)
    assert set(names) == {"Contract", "Customers", "Ticket"}
    assert names["Contract"] == ["CT-2000", "CT-2001", "CT-2002"]
    assert names["Ticket"][0] == "ALPHA-TICKET"
    assert all(len(v) <= 3 for v in names.values())


def test_overview_is_cached_and_dropped_when_the_graph_changes(
        big_workspace: dict[str, Any]) -> None:
    reader = PostgresGraphReader(big_workspace["dsn"], big_workspace["ws"])
    ws = big_workspace["ws"]
    first = build_with_types(reader, ws)
    assert overview_cache.get(ws, 60) == first          # served from cache next time
    after_graph_change(big_workspace["dsn"], ws)         # what an ingest/merge calls
    assert overview_cache.get(ws, 60) is None
    assert build_with_types(reader, ws) == first         # rebuilt from the database


def _ask_prompt(ws: int, monkeypatch: pytest.MonkeyPatch, term: str) -> str:
    """The prompt the answer model receives for a question that finds ``term``."""
    seen: dict[str, str] = {}

    def fake_chat(role: str, system: str, user: str) -> tuple[str, int, int]:
        if role == "menial":
            return '{"terms": ["%s"]}' % term, 1, 1
        seen["prompt"] = user
        return "ok", 1, 1

    monkeypatch.setattr(llm_runtime, "chat", fake_chat)
    app = FastAPI()
    app.include_router(ask_router())
    TestClient(app).post("/ask", json={"question": f"Tell me about {term}",
                                       "workspace_id": ws})
    return seen["prompt"]


def test_safe_mode_keeps_personal_fields_out_of_the_prompt(
        big_workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_facts, "attributes_mode", lambda: "safe")
    prompt = _ask_prompt(big_workspace["ws"], monkeypatch, "Zed Corp")
    assert "Zed Corp [Customers]" in prompt and "tier=gold" in prompt
    assert "zed@example.com" not in prompt and "555-123-4567" not in prompt


def test_all_mode_sends_every_field(
        big_workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_facts, "attributes_mode", lambda: "all")
    prompt = _ask_prompt(big_workspace["ws"], monkeypatch, "Zed Corp")
    assert "email=zed@example.com" in prompt and "phone=555-123-4567" in prompt


def test_off_mode_sends_no_field_values_and_no_breakdown(
        big_workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_facts, "attributes_mode", lambda: "off")
    prompt = _ask_prompt(big_workspace["ws"], monkeypatch, "Zed Corp")
    assert "Zed Corp [Customers]" in prompt             # the record is still found
    assert "tier=gold" not in prompt and "attributes:" not in prompt
    assert f"status: closed {_CLOSED}" not in prompt    # no breakdown either
    assert f"- Ticket: {_TICKETS} records" in prompt    # exact totals still shown
