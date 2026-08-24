"""Data-explorer aggregation tests (v2 Data tab).

Pin the read model the transparency surface renders: per-type counts, the
source breakdown, the dedup story, and entities-by-type carrying attributes +
provenance. Pure functions, no DB.
"""
from __future__ import annotations

from aryx.explore import display_name, entities_view, graph_view, summarize

ENTITIES = [
    (1, "Customer", {"name": "Acme Corp", "tier": "Enterprise"}),
    (2, "Customer", {"name": "Globex"}),
    (3, "Device", {"model": "SM-3000"}),
]
PROV = [
    (1, "postgres", "customers", "c1"),
    (1, "salesforce", "Account", "a1"),   # entity 1 merged from two sources
    (2, "postgres", "customers", "c2"),
    (3, "postgres", "devices", "d1"),
]


def test_display_name_prefers_known_keys_then_falls_back() -> None:
    assert display_name({"name": "Acme"}, 1) == "Acme"
    assert display_name({"model": "SM-3000"}, 3) == "SM-3000"  # first short str
    assert display_name({}, 9) == "#9"


def test_display_name_prefers_name_suffixed_column_over_first_key() -> None:
    """Regression: an Employee row's `manager` field (first key, pure CSV
    column order) must not win over its own `employee_name` just because
    neither is in the exact _NAME_KEYS list."""
    attrs = {"manager": "Arun Kumar", "department": "Engineering",
            "employee_id": "EMP101", "employee_name": "Riya Shah"}
    assert display_name(attrs, 1997) == "Riya Shah"


def test_display_name_name_suffix_generalizes_to_any_dataset() -> None:
    assert display_name({"widget": "gizmo", "customer_name": "Aisha Bello"},
                        1) == "Aisha Bello"


def test_display_name_prefers_own_type_id_over_a_foreign_name_column() -> None:
    """Regression: an Order's own order_id must win over company_name — a
    FOREIGN reference to the Company it belongs to, not this entity's own
    identity. Live bug in workspace orders_new: entities showed "Asha Labs"
    (the company) instead of "O103" (the order's own id)."""
    attrs = {"order_id": "O103", "company_name": "Asha Labs",
            "order_status": "Open", "product_name": "Receipt Printer"}
    assert display_name(attrs, 2764, "Order") == "O103"


def test_display_name_own_type_name_column_still_wins_via_new_tier() -> None:
    """Same Employee case as above, but now WITH ontology_type passed —
    proves the new type-prefixed tier finds employee_name directly rather
    than relying on the generic *_name fallback tier below it."""
    attrs = {"manager": "Arun Kumar", "department": "Engineering",
            "employee_id": "EMP101", "employee_name": "Riya Shah"}
    assert display_name(attrs, 1997, "Employee") == "Riya Shah"


def test_display_name_type_prefixed_name_beats_type_prefixed_id() -> None:
    """When a type has both its own _name and _id column, the human-readable
    name wins — an id is preferred only when no type-owned name exists."""
    attrs = {"widget_id": "W1", "widget_name": "Gizmo"}
    assert display_name(attrs, 1, "Widget") == "Gizmo"


def test_display_name_no_ontology_type_falls_back_to_generic_tier() -> None:
    """Callers that don't pass ontology_type keep the pre-fix behaviour —
    the type-prefixed tier is skipped, not an error."""
    attrs = {"order_id": "O103", "company_name": "Asha Labs"}
    assert display_name(attrs, 2764) == "Asha Labs"


def test_display_name_prefers_declared_match_keys_over_type_prefix_guess() -> None:
    """The actual bug: a SupportTicket ingested with match_keys=["ticket_id"]
    showed "customer_name" (a FOREIGN reference to the ticket's customer)
    because the type-prefix guess (supportticket_id) never matches the real
    column (ticket_id) — no column-naming convention could infer that.
    match_keys is the real ingest-time decision, not a guess, so it must
    win before the type-prefix guess or the generic *_name scan even run."""
    attrs = {"subject": "Azure login failure", "ticket_id": "TK101",
            "company_ref": "Microsoft", "customer_name": "Riya Shah"}
    assert display_name(attrs, 2871, "SupportTicket",
                        match_keys=["ticket_id"]) == "TK101"


def test_display_name_match_keys_prefers_name_shaped_key_over_id_shaped() -> None:
    """A type declared with both a name and an id match key still shows the
    human-readable one — same "prefer name over id" rule as the type-prefix
    tier, just applied within match_keys."""
    attrs = {"employee_id": "EMP101", "employee_name": "Riya Shah",
            "manager": "Arun Kumar"}
    assert display_name(attrs, 1997, "Employee",
                        match_keys=["employee_id", "employee_name"]) == "Riya Shah"


def test_display_name_falls_back_to_type_prefix_when_match_keys_absent() -> None:
    """No stored match_keys (e.g. a dimension-materialized or pre-fix
    entity) — the type-prefix guess still applies as a fallback, unchanged."""
    attrs = {"order_id": "O103", "company_name": "Asha Labs"}
    assert display_name(attrs, 2764, "Order", match_keys=None) == "O103"


def test_display_name_falls_back_to_type_prefix_when_match_key_column_missing() -> None:
    """Declared match_keys that don't actually exist on this record (stale
    metadata, or a record predating a schema change) fall through to the
    type-prefix guess rather than returning nothing."""
    attrs = {"order_id": "O103", "company_name": "Asha Labs"}
    assert display_name(attrs, 2764, "Order", match_keys=["nonexistent_key"]) == "O103"


def test_summary_counts_types_sources_and_dedup() -> None:
    s = summarize(ENTITIES, PROV)
    assert s["total_entities"] == 3
    assert s["type_count"] == 2
    assert s["types"][0] == {"name": "Customer", "count": 2}
    assert s["source_records"] == 4
    assert s["duplicates_merged"] == 1  # 4 source rows -> 3 entities
    srcs = {d["source"]: d["count"] for d in s["sources"]}
    assert srcs["postgres.customers"] == 2


def test_entities_view_filters_by_type_with_provenance() -> None:
    v = entities_view(ENTITIES, PROV, ontology_type="Customer")
    assert v["total"] == 2
    acme = v["items"][0]
    assert acme["name"] == "Acme Corp"
    assert acme["attributes"]["tier"] == "Enterprise"
    assert len(acme["sources"]) == 2  # merged record shows both sources


def test_entities_view_paginates() -> None:
    v = entities_view(ENTITIES, PROV, limit=1, offset=1)
    assert v["total"] == 3
    assert v["offset"] == 1
    assert len(v["items"]) == 1


def test_entities_view_unknown_type_is_empty_not_error() -> None:
    v = entities_view(ENTITIES, PROV, ontology_type="Nope")
    assert v["total"] == 0
    assert v["items"] == []


def test_graph_view_aggregates_edges_by_type_and_name() -> None:
    rels = [(1, 3, "HAS_DEVICE"), (2, 3, "HAS_DEVICE")]  # 2 Customers -> Device
    g = graph_view(ENTITIES, rels)
    assert g["entity_count"] == 3
    assert g["relationship_count"] == 2
    tnodes = {n["type"]: n["count"] for n in g["type_nodes"]}
    assert tnodes == {"Customer": 2, "Device": 1}
    assert g["type_edges"][0] == {"source": "Customer", "target": "Device",
                                  "name": "HAS_DEVICE", "count": 2}


def test_graph_view_ignores_dangling_edges() -> None:
    g = graph_view(ENTITIES, [(1, 999, "X")])  # 999 not an entity
    assert g["type_edges"] == []
