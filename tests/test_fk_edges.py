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
