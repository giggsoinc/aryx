"""Smart understand reads samples THROUGH the customer brief.

The v1.8.0 prompt opened with "You did NOT get a blank brief first" and
drafted a brief cold from column names. Brief-first inverts that: the
customer's brief is supplied as authoritative context, echoed back on the
result untouched, and survives even the offline heuristic path.
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

# Stub the DB drivers ONLY when genuinely absent — an unconditional stub
# would poison sys.modules for every later test module in the process.
for _mod in ("falkordb", "psycopg", "psycopg.types", "psycopg.types.json",
             "psycopg_pool"):
    try:
        importlib.import_module(_mod)
    except ImportError:
        sys.modules.setdefault(_mod, MagicMock())

import pytest

from aryx.pipeline import smart_understand

_BRIEF = {
    "domain": "Retail banking",
    "aim": "Spot card fraud within a day",
    "objectives": ["cut false positives"],
    "scope": "IN: card transactions",
    "roles": ["Fraud analyst"],
    "questions": ["which merchants spike overnight?"],
}

_SAMPLES = [{
    "filename": "txns.csv",
    "kind": "tabular",
    "columns": ["date", "description", "amount", "category"],
    "sample_text": "date,description,amount,category\n2026-01-02,ACME,12.00,food",
    "row_estimate": 900,
}]


def test_system_prompt_no_longer_assumes_a_blank_brief() -> None:
    """The 1.8.0 framing is what made the brief data-derived."""
    assert "You did NOT get a blank brief first" not in smart_understand._SYSTEM
    assert "BEFORE uploading" in smart_understand._SYSTEM
    assert "never to replace it" in smart_understand._SYSTEM


def test_customer_brief_is_sent_to_the_model_as_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    payload = (
        '{"summary": "card transactions", "brief": {"domain": "Card spend"}, '
        '"graph_plan": {}, "divergences": ["no fraud label"], '
        '"gaps": ["no timestamp for overnight"]}'
    )

    def _chat(_role: str, _system: str, user: str):
        seen["user"] = user
        return payload, "m", {}

    monkeypatch.setattr(smart_understand.llm_runtime, "chat", _chat)
    result = smart_understand.understand_samples(_SAMPLES, customer_brief=_BRIEF)

    assert "Customer brief (authoritative)" in seen["user"]
    assert "Spot card fraud within a day" in seen["user"]
    assert "which merchants spike overnight?" in seen["user"]
    # The derived reading and the customer brief stay distinguishable.
    assert result["brief"]["domain"] == "Card spend"
    assert result["customer_brief"] == _BRIEF
    assert result["divergences"] == ["no fraud label"]
    assert result["gaps"] == ["no timestamp for overnight"]


def test_no_customer_brief_still_drafts_cold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Soft gate: a skipped brief must not break understand."""
    payload = (
        '{"summary": "s", "brief": {"domain": "Transactions"}, "graph_plan": {}}'
    )
    monkeypatch.setattr(smart_understand.llm_runtime, "chat",
                        lambda *a, **k: (payload, "m", {}))
    result = smart_understand.understand_samples(_SAMPLES)

    assert result["brief"]["domain"] == "Transactions"
    assert result["customer_brief"] == {}


def test_offline_fallback_keeps_the_customer_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no model reachable, the heuristic must not overwrite the brief."""
    def _boom(*_a, **_k):
        raise RuntimeError("no provider configured")

    monkeypatch.setattr(smart_understand.llm_runtime, "chat", _boom)
    result = smart_understand.understand_samples(_SAMPLES, customer_brief=_BRIEF)

    assert result["fallback"] is True
    # Filename heuristics would have said "Personal banking" — the customer wins.
    assert result["brief"]["domain"] == "Retail banking"
    assert result["brief"]["aim"] == "Spot card fraud within a day"
    assert result["brief"]["questions"] == ["which merchants spike overnight?"]
    assert result["brief"]["objectives"] == ["cut false positives"]
    assert result["customer_brief"] == _BRIEF


def test_offline_fallback_without_a_brief_uses_heuristics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        smart_understand.llm_runtime, "chat",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    result = smart_understand.understand_samples(_SAMPLES)

    assert result["fallback"] is True
    assert result["brief"]["domain"]  # heuristic still produces something
    assert result["customer_brief"] == {}


def test_empty_samples_return_the_full_contract() -> None:
    result = smart_understand.understand_samples([])

    for field in ("summary", "brief", "graph_plan", "customer_brief",
                  "divergences", "gaps", "fallback"):
        assert field in result


def test_result_carries_the_servers_populated_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The UI must not re-derive "is this brief real?".

    SmartReview used to compute it from Object.values(customer_brief),
    which counted `source_docs` — so a brief holding only a filename read
    as populated in the UI while the server promoted the derived one over
    it. The server now ships its own is_populated verdict.
    """
    payload = '{"summary": "s", "brief": {}, "graph_plan": {}}'
    monkeypatch.setattr(smart_understand.llm_runtime, "chat",
                        lambda *a, **k: (payload, "m", {}))

    real = smart_understand.understand_samples(_SAMPLES, customer_brief=_BRIEF)
    docs_only = smart_understand.understand_samples(
        _SAMPLES, customer_brief={"source_docs": ["sow.pdf"]})

    assert real["customer_brief_populated"] is True
    assert docs_only["customer_brief_populated"] is False
    assert smart_understand.understand_samples([])["customer_brief_populated"] is False


def test_offline_fallback_also_reports_the_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All three result shapes carry it, or the UI sees undefined."""
    monkeypatch.setattr(
        smart_understand.llm_runtime, "chat",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))

    result = smart_understand.understand_samples(_SAMPLES, customer_brief=_BRIEF)
    assert result["fallback"] is True
    assert result["customer_brief_populated"] is True
