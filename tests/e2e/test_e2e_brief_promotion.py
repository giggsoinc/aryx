"""The guarded brief promote, against real Postgres.

`promote_derived_brief.sql` is the atomic form of the soft gate: adopt the
model's reading as the brief ONLY while the customer has none. Its WHERE
clause has to agree, in SQL, with `aryx.brief.is_populated` in Python —
blank scalars, empty/whitespace list entries, and `source_docs` (which is
provenance, not an authored brief) all count as "no brief".

The unit tests exercise this through a fake store that reimplements the
guard in Python, so they prove `record()`'s branching but say nothing about
the SQL itself. These tests run the real statement against the real column
types, so editing that predicate cannot silently break the one invariant
brief-first exists to hold.
"""
from __future__ import annotations

from typing import Any

import pytest

from aryx.brief import is_populated
from aryx.workspaces import WorkspaceStore

pytestmark = pytest.mark.e2e

_DERIVED = {"domain": "Derived reading", "aim": "Summarise the columns"}

# (label, brief) pairs that aryx.brief.is_populated calls EMPTY. The SQL
# predicate must agree with every one of them.
_EMPTY_BRIEFS: list[tuple[str, dict[str, Any]]] = [
    ("no brief at all", {}),
    ("blank scalars", {"domain": "  ", "aim": "", "scope": ""}),
    ("empty lists", {"objectives": [], "roles": [], "questions": []}),
    ("whitespace list entries", {"roles": ["  ", ""]}),
    ("source_docs only", {"source_docs": ["sow.pdf"]}),
]

# ...and the ones it calls POPULATED, which must be left untouched.
_REAL_BRIEFS: list[tuple[str, dict[str, Any]]] = [
    ("domain only", {"domain": "Retail banking"}),
    ("aim only", {"aim": "Spot card fraud"}),
    ("scope only", {"scope": "IN: transactions"}),
    ("objectives only", {"objectives": ["cut false positives"]}),
    ("roles only", {"roles": ["Fraud analyst"]}),
    ("questions only", {"questions": ["which merchants spike?"]}),
]


@pytest.fixture
def store(e2e_dsn: str) -> Any:
    """A WorkspaceStore on the live database."""
    s = WorkspaceStore(e2e_dsn)
    try:
        yield s
    finally:
        s.close()


@pytest.mark.parametrize(("label", "brief"), _EMPTY_BRIEFS,
                         ids=[label for label, _ in _EMPTY_BRIEFS])
def test_promote_succeeds_when_the_brief_is_empty(
    store: Any, workspace: dict, label: str, brief: dict,
) -> None:
    """Soft gate: a customer who skipped the brief gets the derived one."""
    wid = workspace["id"]
    store.set_brief(wid, brief)
    assert is_populated(brief) is False, "fixture drift: Python says populated"

    row = store.promote_derived_brief(wid, _DERIVED)

    assert row is not None, f"SQL refused to promote over {label!r}"
    assert row["brief"]["domain"] == "Derived reading"
    assert row["brief_source"] == "derived"
    assert store.get_understanding(wid)["brief_source"] == "derived"


@pytest.mark.parametrize(("label", "brief"), _REAL_BRIEFS,
                         ids=[label for label, _ in _REAL_BRIEFS])
def test_promote_refuses_over_a_real_customer_brief(
    store: Any, workspace: dict, label: str, brief: dict,
) -> None:
    """The invariant: one populated field is enough to protect the brief."""
    wid = workspace["id"]
    store.set_brief(wid, brief)
    assert is_populated(brief) is True, "fixture drift: Python says empty"

    row = store.promote_derived_brief(wid, _DERIVED)

    assert row is None, f"SQL overwrote a real brief ({label})"
    after = store.get_understanding(wid)
    assert after["brief"] == brief
    assert after["brief_source"] == "customer"


def test_promote_is_atomic_under_a_lost_race(
    store: Any, workspace: dict,
) -> None:
    """Second promote must lose once the first has landed.

    Stands in for the real TOCTOU: two ingests (or an ingest and a customer
    save) racing on a workspace that started with no brief. Exactly one may
    win, and the loser must not clobber the winner.
    """
    wid = workspace["id"]
    store.set_brief(wid, {})

    first = store.promote_derived_brief(wid, _DERIVED)
    second = store.promote_derived_brief(wid, {"domain": "Second reading"})

    assert first is not None
    assert second is None, "a second promote overwrote the first"
    assert store.get_understanding(wid)["brief"]["domain"] == "Derived reading"


def test_a_human_save_reclaims_authorship_after_promotion(
    store: Any, workspace: dict,
) -> None:
    """A derived brief is not a life sentence — editing it makes it yours."""
    wid = workspace["id"]
    store.set_brief(wid, {})
    store.promote_derived_brief(wid, _DERIVED)

    store.set_brief(wid, {"domain": "Customer authored"})
    store.set_brief_source(wid, "customer")

    after = store.get_understanding(wid)
    assert after["brief_source"] == "customer"
    assert store.promote_derived_brief(wid, _DERIVED) is None
