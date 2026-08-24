"""_relationship_direction: correct an LLM-stated relationship's from/to
against dimension_types (the authority on which side owns via_column).

Regression: a graph_plan with {"from": "Company", "to": "Order",
"via_column": "company_name"} silently produced zero Order->Company edges,
because company_name is an Order column, not a Company one — neither side
of the stated pair actually carried it, so link_by_attribute matched
nothing. Two sibling relationships in the same plan happened to already be
in the correct direction, which is why only this one went missing.
"""
from __future__ import annotations

from aryx.pipeline.dimension_materialize import _relationship_direction

_DIMS = {
    "Company": {"name": "Company", "role": "dimension",
               "from_type": "Order", "source_column": "company_name"},
    "Product": {"name": "Product", "role": "dimension",
               "from_type": "Order", "source_column": "product_name"},
}


def test_reversed_relationship_gets_corrected() -> None:
    """The exact bug: from/to swapped relative to dimension_types."""
    rel = {"from": "Company", "to": "Order",
           "name": "PLACED_ORDER", "via_column": "company_name"}
    src, tgt, via, name = _relationship_direction(rel, _DIMS)
    assert (src, tgt, via, name) == ("Order", "Company", "company_name", "PLACED_ORDER")


def test_already_correct_relationship_is_unchanged() -> None:
    """A relationship already in FK-carrier order must pass through as-is."""
    rel = {"from": "Order", "to": "Product",
           "name": "INCLUDES_PRODUCT", "via_column": "product_name"}
    src, tgt, via, name = _relationship_direction(rel, _DIMS)
    assert (src, tgt, via, name) == ("Order", "Product", "product_name", "INCLUDES_PRODUCT")


def test_no_matching_dimension_trusts_the_stated_direction() -> None:
    """No dimension agrees on via_column -> leave from/to exactly as given
    (e.g. a non-dimension relationship the plan declared directly)."""
    rel = {"from": "Ticket", "to": "Agent",
           "name": "ASSIGNED_TO", "via_column": "agent_email"}
    src, tgt, via, name = _relationship_direction(rel, _DIMS)
    assert (src, tgt, via, name) == ("Ticket", "Agent", "agent_email", "ASSIGNED_TO")


def test_dimension_agrees_on_name_but_not_column_is_left_alone() -> None:
    """A same-named dimension that disagrees on via_column is not a match —
    don't blindly rewrite direction just because the type name coincides."""
    rel = {"from": "Company", "to": "Order",
           "name": "PLACED_ORDER", "via_column": "customer_company"}
    src, tgt, via, name = _relationship_direction(rel, _DIMS)
    assert (src, tgt, via, name) == ("Company", "Order", "customer_company", "PLACED_ORDER")


def test_default_edge_name_from_types_when_unnamed() -> None:
    """No explicit name -> falls back to {from}_{to} (pre-correction), same
    as the un-refactored inline behavior."""
    rel = {"from": "Company", "to": "Order", "via_column": "company_name"}
    _src, _tgt, _via, name = _relationship_direction(rel, _DIMS)
    assert name == "COMPANY_ORDER"
