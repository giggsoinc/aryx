"""Ask accuracy: exact counts, record attributes, value breakdowns.

Regression tests for the "Ask answers wrong / cannot answer" bug:

* the overview counted the first 500 entities and reported that as the total
  (600 contracts showed as 460, and later types vanished entirely);
* the model was shown a record's name and links but none of its fields
  (status, priority, amount), so it guessed;
* a model that ran out of tokens mid-<think> had its private reasoning shown
  to the user as if it were the answer.

Pure logic with a fake reader — no database, no LLM.
"""
from __future__ import annotations

from typing import Any

from aryx.api.ask_api import _strip_think
from aryx.api.ask_overview import _kinds
from aryx.ask.evidence import RetrievedEntity
from aryx.graph import ask_facts
from aryx.graph.ask_facts import (
    format_attributes, format_breakdown, summarise_neighbors, type_counts,
)
from aryx.graph.retrieve import all_types, render_context


class _CappedOnlyReader:
    """An adapter with only the original methods: a 500-row ``find_entities``."""

    def __init__(self, entities: list[dict[str, Any]]) -> None:
        self._entities = entities

    def find_entities(self, ontology_type: str | None = None,
                      name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        rows = [e for e in self._entities
                if not ontology_type or e["type"] == ontology_type]
        return rows[:min(limit, 500)]


class _ExactReader(_CappedOnlyReader):
    """The Postgres reader's shape: adds exact counts and breakdowns."""

    def __init__(self, entities: list[dict[str, Any]],
                 counts: dict[str, int],
                 breakdown: dict[str, dict[str, dict[str, int]]] | None = None) -> None:
        super().__init__(entities)
        self._counts = counts
        self._breakdown = breakdown or {}

    def count_by_type(self) -> dict[str, int]:
        return self._counts

    def attribute_breakdown(self, max_values: int = 8) -> dict[str, dict[str, dict[str, int]]]:
        return self._breakdown


def _workspace_over_the_cap() -> list[dict[str, Any]]:
    """40 customers, 600 contracts, 160 tickets — ids ascending in that order."""
    rows: list[dict[str, Any]] = []
    for kind, n in (("Customers", 40), ("Contract", 600), ("Ticket", 160)):
        for i in range(n):
            rows.append({"id": len(rows) + 1, "type": kind, "name": f"{kind}-{i}"})
    return rows


# --- exact counts (the 500-row cap) ---------------------------------------

def test_overview_reports_exact_totals_past_the_500_row_cap() -> None:
    """600 contracts and 160 tickets must not shrink to 460 and 0."""
    reader = _ExactReader(_workspace_over_the_cap(),
                          {"Contract": 600, "Customers": 40, "Ticket": 160})
    text = "\n".join(_kinds(reader, 1))
    assert "- Contract: 600 records" in text
    assert "- Ticket: 160 records" in text
    assert "- Customers: 40 records" in text
    assert "at least" not in text


def test_overview_samples_names_per_type_not_from_the_capped_list() -> None:
    """Ticket names must appear even though no ticket is in the first 500 rows."""
    reader = _ExactReader(_workspace_over_the_cap(),
                          {"Contract": 600, "Customers": 40, "Ticket": 160})
    ticket_line = next(line for line in _kinds(reader, 1) if "- Ticket:" in line)
    assert "Ticket-0" in ticket_line


def test_adapter_without_count_by_type_falls_back_and_says_at_least() -> None:
    """A swapped-in adapter keeps working, but must not claim a false total."""
    reader = _CappedOnlyReader(_workspace_over_the_cap())
    counts, exact = type_counts(reader)
    assert exact is False
    assert counts == {"Customers": 40, "Contract": 460}
    text = "\n".join(_kinds(reader, 1))
    assert "- Contract: at least 460 records" in text


def test_failing_count_query_falls_back_to_the_sample() -> None:
    """A DB hiccup degrades the answer; it must not raise into Ask."""
    class _Broken(_CappedOnlyReader):
        def count_by_type(self) -> dict[str, int]:
            raise RuntimeError("connection reset")

    counts, exact = type_counts(_Broken(_workspace_over_the_cap()))
    assert exact is False
    assert "Contract" in counts


def test_all_types_lists_a_type_that_only_exists_past_the_cap() -> None:
    reader = _ExactReader(_workspace_over_the_cap(),
                          {"Contract": 600, "Customers": 40, "Ticket": 160})
    assert all_types(reader) == ["Contract", "Customers", "Ticket"]


def test_empty_workspace_overview_is_empty() -> None:
    assert _kinds(_ExactReader([], {})) == []


# --- value breakdowns ("how many tickets are open?") ----------------------

def test_overview_includes_value_breakdown_lines() -> None:
    reader = _ExactReader(
        _workspace_over_the_cap(),
        {"Contract": 600, "Customers": 40, "Ticket": 160},
        {"Ticket": {"status": {"open": 53, "closed": 107},
                    "priority": {"low": 128, "high": 32}}})
    lines = _kinds(reader, 1)
    assert "      priority: low 128, high 32" in lines
    assert "      status: closed 107, open 53" in lines


def test_format_breakdown_orders_by_count_then_value() -> None:
    assert format_breakdown({"status": {"b": 2, "a": 2, "c": 9}}) == [
        "status: c 9, a 2, b 2"]


def test_format_breakdown_caps_the_number_of_keys() -> None:
    many = {f"k{i}": {"v": 1} for i in range(20)}
    assert len(format_breakdown(many)) == ask_facts.MAX_BREAKDOWN_KEYS


# --- record attributes ("what is ticket T-5's status?") -------------------

def test_format_attributes_shows_fields_the_model_needs() -> None:
    text = format_attributes(
        {"ticket_id": "TKT-5003", "status": "open", "priority": "low"}, "TKT-5003")
    assert "status=open" in text and "priority=low" in text


def test_format_attributes_drops_noise() -> None:
    text = format_attributes(
        {"name": "Acme", "note": "", "gone": None, "nested": {"a": 1},
         "tags": ["x"], "tier": "gold"}, "Acme")
    assert text == "tier=gold"


def test_format_attributes_truncates_long_values_and_caps_count() -> None:
    attrs = {f"k{i:02d}": "x" * 200 for i in range(30)}
    text = format_attributes(attrs)
    parts = text.split(", ")
    assert len(parts) == ask_facts.MAX_ATTRIBUTES
    assert all(len(p.split("=", 1)[1]) <= ask_facts.MAX_VALUE_CHARS for p in parts)


def test_entity_attributes_fails_soft_without_the_method() -> None:
    ent = RetrievedEntity(id=1, type="Ticket", name="T")
    assert ask_facts.entity_attributes(_CappedOnlyReader([]), [ent]) == {}


def test_entity_attributes_fails_soft_on_query_error() -> None:
    class _Broken(_CappedOnlyReader):
        def entity_attributes(self, entity_ids: list[int]) -> dict[int, dict[str, Any]]:
            raise RuntimeError("boom")

    ent = RetrievedEntity(id=1, type="Ticket", name="T")
    assert ask_facts.entity_attributes(_Broken([]), [ent]) == {}


# --- render_context -------------------------------------------------------

def _customer(neighbors: int = 3) -> RetrievedEntity:
    links = [{"id": 100 + i, "type": "Contract", "name": f"CT-{i}",
              "relationship": "CONTRACT_CUSTOMERS", "direction": "in"}
             for i in range(neighbors)]
    links.append({"id": 900, "type": "Ticket", "name": "TKT-1",
                  "relationship": "TICKET_CUSTOMERS", "direction": "in"})
    return RetrievedEntity(id=7, type="Customers", name="Zephyr Dynamics",
                           neighbors=links, sources=[])


def test_render_context_default_output_is_unchanged() -> None:
    """The frozen golden test pins this exact text — extras must be opt-in."""
    text = render_context([_customer(2)])
    assert text == (
        "Zephyr Dynamics [Customers] (id 7)\n"
        "  <- CONTRACT_CUSTOMERS CT-0 [Contract]\n"
        "  <- CONTRACT_CUSTOMERS CT-1 [Contract]\n"
        "  <- TICKET_CUSTOMERS TKT-1 [Ticket]")


def test_render_context_adds_attributes_and_link_totals() -> None:
    text = render_context([_customer(10)],
                          attributes={7: {"tier": "enterprise", "city": "Denver"}},
                          summarise=True)
    assert "  attributes: tier=enterprise, city=Denver" in text
    assert "  linked: 10 x Contract (<- CONTRACT_CUSTOMERS), 1 x Ticket (<- TICKET_CUSTOMERS)" in text


def test_render_context_caps_listed_links_but_keeps_true_totals() -> None:
    text = render_context([_customer(60)], summarise=True)
    assert "60 x Contract" in text          # total is exact
    assert text.count("CONTRACT_CUSTOMERS CT-") + text.count("TICKET_CUSTOMERS TKT-") \
        == ask_facts.MAX_NEIGHBORS
    assert "... and 36 more linked records" in text


def test_summarise_neighbors_counts_by_relationship_direction_and_type() -> None:
    n = [{"relationship": "R", "direction": "out", "type": "A"}] * 3
    n += [{"relationship": "R", "direction": "in", "type": "A"}]
    assert summarise_neighbors(n) == "3 x A (-> R), 1 x A (<- R)"


# --- unterminated <think> -------------------------------------------------

def test_strip_think_keeps_the_answer_after_a_closed_block() -> None:
    assert _strip_think("<think>hmm</think>There are 3.") == "There are 3."


def test_strip_think_passes_plain_text_through() -> None:
    assert _strip_think("There are 3.") == "There are 3."


def test_strip_think_returns_nothing_when_the_model_never_finished_thinking() -> None:
    """Cut off mid-thought: the monologue must not be shown as the answer."""
    assert _strip_think("<think> Okay, let's tackle this. The user asks") == ""
