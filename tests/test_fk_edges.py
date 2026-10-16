"""link_by_attribute's Relationship direction must match its own source_type/target_type naming — the edge
points FROM the source_type entity TO the target_type entity, not reversed.
"""
from __future__ import annotations

from aryx.pipeline.fk_edges import link_by_attribute


class FakeEntityStore:
    """Minimal EntityStore stub: fixed entity list, captures saved edges."""

    def __init__(self, entities: list[tuple[int, str, dict]]) -> None:
        self._entities = entities
        self.saved: list = []

    def list_entities(self) -> list[tuple[int, str, dict]]:
        return self._entities

    def save_relationships(self, rels: list) -> None:
        self.saved.extend(rels)


def test_edge_points_from_source_type_to_target_type() -> None:
    """A SupportTicket referencing a Customer by name -> edge ticket -> customer,
    i.e. source_entity_id is the SupportTicket's id (sid), target_entity_id is
    the Customer's id (tid) — matching the source_type/target_type params."""
    entities = [
        (1, "Customer", {"name": "Acme Corp"}),
        (2, "SupportTicket", {"customer_name": "Acme Corp"}),
    ]
    store = FakeEntityStore(entities)

    count = link_by_attribute(store, "SupportTicket", "customer_name",
                              "Customer", "name", "HAS_TICKET")

    assert count == 1
    rel = store.saved[0]
    assert rel.source_entity_id == 2, "source_entity_id must be the SupportTicket (source_type)"
    assert rel.target_entity_id == 1, "target_entity_id must be the Customer (target_type)"
    assert rel.name == "HAS_TICKET"


def test_self_typed_symmetric_match_emits_one_edge_not_two() -> None:
    """Regression: when source_type == target_type and source_attr ==
    target_attr (matching the SAME field on the SAME type against itself —
    e.g. two Customer-typed rows sharing a CustomerID because upstream
    typing collapsed distinct real-world kinds into one type), the equality
    match is symmetric: A.CustomerID == B.CustomerID implies B.CustomerID ==
    A.CustomerID. The nested loop visits the pair from both sides, so
    without a guard this emits (A,B) AND (B,A) for what is one logical edge.
    """
    entities = [
        (1, "Customer", {"CustomerID": "1", "Name": "John Smith"}),
        (2, "Customer", {"CustomerID": "1", "Issue": "Radio not booting"}),
    ]
    store = FakeEntityStore(entities)

    count = link_by_attribute(store, "Customer", "CustomerID",
                              "Customer", "CustomerID", "CUSTOMER_CUSTOMER")

    assert count == 1, f"expected exactly one edge for a symmetric self-match, got {count}"


def test_self_typed_symmetric_match_three_way_group() -> None:
    """Three same-typed entities sharing one key must produce exactly the
    3 unordered pairs (C(3,2)=3), not 6 (both directions of each pair)."""
    entities = [
        (1, "Customer", {"CustomerID": "9"}),
        (2, "Customer", {"CustomerID": "9"}),
        (3, "Customer", {"CustomerID": "9"}),
    ]
    store = FakeEntityStore(entities)

    count = link_by_attribute(store, "Customer", "CustomerID",
                              "Customer", "CustomerID", "SAME_GROUP")

    assert count == 3


def test_self_typed_asymmetric_match_is_not_deduped() -> None:
    """When source_attr != target_attr on a self-typed link (e.g. an org
    chart: manager_id vs employee_id), the match is directional by
    construction and pairs are NOT naturally doubled — the dedup guard must
    not remove a legitimate directed self-referential edge."""
    entities = [
        (1, "Employee", {"employee_id": "e1", "manager_id": "e2"}),
        (2, "Employee", {"employee_id": "e2", "manager_id": None}),
    ]
    store = FakeEntityStore(entities)

    count = link_by_attribute(store, "Employee", "manager_id",
                              "Employee", "employee_id", "REPORTS_TO")

    assert count == 1
    rel = store.saved[0]
    assert rel.source_entity_id == 1  # the employee (sid) reports to their manager (tid)
    assert rel.target_entity_id == 2
