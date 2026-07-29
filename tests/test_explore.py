"""Data-explorer aggregation tests (v2 Data tab).

Pin the read model the transparency surface renders: per-type counts, the
source breakdown, the dedup story, and entities-by-type carrying attributes +
provenance. Pure functions, no DB.
"""
from __future__ import annotations

from aryx.explore import (
    display_name,
    entities_view,
    entity_detail,
    entity_graph_view,
    graph_view,
    summarize,
)

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


def test_materialized_hierarchy_uses_real_edges_and_line_labels() -> None:
    entities = [
        (10, "ParentItem", {"parent_key": "P-1", "child_key": "1"}),
        (11, "ParentItem", {"parent_key": "P-1", "child_key": "2"}),
        (20, "Parent", {"parent_key": "P-1", "name": "P-1"}),
    ]
    rels = [(20, 10, "HAS_PARENTITEM"), (20, 11, "HAS_PARENTITEM")]

    g = entity_graph_view(
        entities, rels, hub_attr="parent_key", label_attr="child_key")

    assert not any(str(n["id"]).startswith("hub:") for n in g["nodes"])
    assert {n["name"] for n in g["nodes"] if n["type"] == "ParentItem"} == {"1", "2"}
    assert g["relationship_count"] == 2


def test_entity_detail_title_uses_label_attr_without_duplicate_synthetic_hub() -> None:
    entities = [
        (10, "ParentItem", {"parent_key": "P-1", "child_key": "1"}),
        (20, "Parent", {"parent_key": "P-1", "name": "P-1"}),
    ]
    detail = entity_detail(
        entities, [], [(20, 10, "HAS_PARENTITEM")], 10,
        hub_attr="parent_key", label_attr="child_key")

    assert detail is not None
    assert detail["name"] == "1"
    assert detail["relationships"] == [{
        "direction": "in",
        "name": "HAS_PARENTITEM",
        "other_id": 20,
        "other_name": "P-1",
        "other_type": "Parent",
    }]


def test_named_grouping_does_not_relabel_mixed_types() -> None:
    entities = [
        (10, "Customer", {"parent_key": "P-1", "name": "Customer A"}),
        (11, "Order", {"parent_key": "P-1", "name": "Order A"}),
    ]

    g = entity_graph_view(entities, [], hub_attr="parent_key")

    assert {n["type"] for n in g["nodes"]} == {"Customer", "Order"}
    assert g["edges"] == []


def test_same_type_group_detail_does_not_add_phantom_parent() -> None:
    entities = [
        (10, "Transaction", {"account_key": "A-1", "name": "T-1"}),
    ]

    detail = entity_detail(entities, [], [], 10, hub_attr="account_key")

    assert detail is not None
    assert detail["relationships"] == []
