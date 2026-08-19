"""Brief-first architecture: the customer brief outranks the derived reading.

The one rule this module exists to hold: nothing in the ingest path may
overwrite a brief the customer authored before uploading. The derived
reading of the data lands in `data_understanding` and stays read-only.
The single exception is the soft gate — an empty customer brief gets the
derived reading promoted into it, stamped `brief_source='derived'`.
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

# Stub the DB drivers ONLY when they are genuinely not installed, so
# aryx.understanding still imports on a bare checkout. Stubbing them
# unconditionally would leave a MagicMock in sys.modules for the rest of the
# pytest process and break every later module that needs the real driver
# (e.g. `from psycopg.errors import UniqueViolation`).
for _mod in ("falkordb", "psycopg", "psycopg.types", "psycopg.types.json",
             "psycopg_pool"):
    try:
        importlib.import_module(_mod)
    except ImportError:
        sys.modules.setdefault(_mod, MagicMock())

from aryx import understanding

_CUSTOMER = {
    "domain": "Retail banking",
    "aim": "Spot card fraud within a day of the transaction",
    "objectives": ["cut false positives"],
    "scope": "IN: card transactions  OUT: HR records",
    "roles": ["Fraud analyst"],
    "questions": ["which merchants spike overnight?"],
}

_DERIVED = {
    "domain": "Transaction log",
    "aim": "Summarise rows in the uploaded CSV",
    "objectives": ["count rows per column"],
    "scope": "IN: csv columns",
    "roles": ["Analyst"],
    "questions": ["how many rows are there?"],
}


class _FakeStore:
    """Minimal WorkspaceStore stand-in recording every write."""

    def __init__(self, brief: dict | None = None) -> None:
        self._brief = dict(brief or {})
        self.understanding: dict = {}
        self.brief_writes: list[dict] = []
        self.brief_source = "customer"
        self.promoted: dict | None = None
        self.context = ""

    def get_understanding(self, wid: int) -> dict:
        return {"brief": self._brief, "data_understanding": self.understanding,
                "brief_source": self.brief_source}

    def set_understanding(self, wid: int, payload: dict) -> dict:
        self.understanding = payload
        return {"id": wid, "data_understanding": payload}

    def set_brief(self, wid: int, brief: dict) -> dict:
        self.brief_writes.append(brief)
        self._brief = dict(brief)
        return {"id": wid, "brief": brief}

    def promote_derived_brief(self, wid: int, brief: dict) -> dict | None:
        """Guarded promote — succeeds only while the brief is empty."""
        from aryx.brief import is_populated
        if is_populated(self._brief):
            return None
        self.promoted = dict(brief)
        self._brief = dict(brief)
        self.brief_source = "derived"
        return {"id": wid, "brief": brief, "brief_source": "derived"}

    def set_brief_source(self, wid: int, source: str) -> str:
        self.brief_source = source
        return source

    def set_context(self, wid: int, context: str) -> dict:
        self.context = context
        return {"id": wid, "context": context}


def test_populated_customer_brief_is_never_overwritten() -> None:
    """The regression this whole change exists to fix."""
    store = _FakeStore(_CUSTOMER)

    outcome = understanding.record(store, 1, _DERIVED, {}, {})

    assert store.brief_writes == [], "derived reading must not touch the brief"
    assert store.brief_source == "customer"
    assert outcome["brief"] == _CUSTOMER
    assert outcome["brief_source"] == "customer"
    assert outcome["promoted"] is False


def test_derived_reading_is_stored_separately_and_stays_readable() -> None:
    store = _FakeStore(_CUSTOMER)

    understanding.record(store, 1, _DERIVED, {"outcomes": ["browse"]},
                         {"summary": "A card transaction export.",
                          "divergences": ["no fraud label column"],
                          "gaps": ["cannot answer overnight spikes — no timestamp"]},
                         ["txns.csv"])

    stored = store.understanding
    assert stored["brief"] == _DERIVED
    assert stored["summary"] == "A card transaction export."
    assert stored["divergences"] == ["no fraud label column"]
    assert stored["gaps"] == ["cannot answer overnight spikes — no timestamp"]
    assert stored["source_files"] == ["txns.csv"]
    assert stored["promoted_to_brief"] is False
    assert stored["generated_at"]


def test_empty_customer_brief_promotes_the_derived_reading() -> None:
    """Soft gate: skipping the brief grounds ingest in the derived one."""
    store = _FakeStore({})

    outcome = understanding.record(store, 1, _DERIVED, {}, {})

    # Promotion travels through the guarded UPDATE, never plain set_brief —
    # only the guarded path can lose the race safely.
    assert store.promoted == _DERIVED
    assert store.brief_writes == []
    assert store.brief_source == "derived"
    assert outcome["brief"] == _DERIVED
    assert outcome["brief_source"] == "derived"
    assert outcome["promoted"] is True
    assert store.understanding["promoted_to_brief"] is True


def test_blank_valued_customer_brief_counts_as_empty() -> None:
    """A brief of empty strings is skipped, not authored — promote over it."""
    store = _FakeStore({"domain": "  ", "aim": "", "objectives": [],
                        "scope": "", "roles": [], "questions": []})

    outcome = understanding.record(store, 1, _DERIVED, {}, {})

    assert outcome["promoted"] is True
    assert store.brief_source == "derived"


def test_textarea_lists_are_coerced_before_storage() -> None:
    store = _FakeStore(_CUSTOMER)

    understanding.record(store, 1,
                         {**_DERIVED, "objectives": "one\n  two  \n\n"}, {}, {})

    assert store.understanding["brief"]["objectives"] == ["one", "two"]


def test_plan_context_is_written_from_the_customer_brief() -> None:
    """Extractors must inherit the customer's domain, not the derived one."""
    store = _FakeStore(_CUSTOMER)

    understanding.stash_plan_context(store, 1, _CUSTOMER, {
        "outcomes": ["spot fraud"],
        "primary_types": [{"name": "Transaction"}],
        "dimension_types": [{"name": "Merchant"}],
    })

    assert "Domain: Retail banking" in store.context
    assert "Transaction" in store.context and "Merchant" in store.context
    assert "Transaction log" not in store.context


def test_customer_brief_lookup_survives_a_store_failure() -> None:
    """Understanding is an enrichment — a DB hiccup must not block ingest."""
    class _Broken(_FakeStore):
        def get_understanding(self, wid: int) -> dict:
            raise RuntimeError("connection reset")

    assert understanding.customer_brief(_Broken(), 1) == {}


# --- race: the customer brief must survive a save mid-ingest ---------------

class _RacingStore(_FakeStore):
    """A store where the customer's brief lands DURING record()."""

    def promote_derived_brief(self, wid: int, brief: dict) -> dict | None:
        # The guarded UPDATE matches zero rows because a real brief arrived
        # after record() read an empty one.
        self._brief = dict(_CUSTOMER)
        self.brief_source = "customer"
        return None


def test_customer_brief_saved_mid_ingest_is_not_overwritten() -> None:
    """TOCTOU guard.

    record() used to read the brief, decide `promoted`, then write. A
    customer saving inside that window had their brief replaced by the
    model's reading — the one thing brief-first must never do. The promote
    is now a single guarded UPDATE, and a zero-row result means someone
    else won.
    """
    store = _RacingStore({})

    outcome = understanding.record(store, 1, _DERIVED, {}, {})

    assert store._brief == _CUSTOMER, "the customer's brief was overwritten"
    assert store.brief_source == "customer"
    assert outcome["promoted"] is False
    assert outcome["brief_source"] == "customer"
    # The caller must be told what SURVIVED, not the stale pre-race read.
    assert outcome["brief"] == _CUSTOMER


def test_promotion_goes_through_the_guarded_update_not_set_brief() -> None:
    """set_brief must not be used for promotion — it cannot be guarded."""
    store = _FakeStore({})

    understanding.record(store, 1, _DERIVED, {}, {})

    assert store.brief_writes == [], "promotion bypassed the guarded UPDATE"
    assert store.promoted == _DERIVED
