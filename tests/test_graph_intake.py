"""Tests for Knowledge Graph Intake & Validation (C05) — pure, no DB."""
from __future__ import annotations

from aryx.graph_intake import build_graph_json, validate_and_normalize

GOOD = {
    "entities": [
        {"id": "customer_CU209", "type": "Customer"},
        {"id": "contract_C1001", "type": "Contract"},
        {"id": "manager_ASmith", "type": "AccountManager"},
    ],
    "relationships": [
        {"source": "customer_CU209", "type": "HAS_CONTRACT", "target": "contract_C1001"},
        {"source": "contract_C1001", "type": "MANAGED_BY", "target": "manager_ASmith"},
    ],
}


def _run(graph, gid="graph_contracts", ver="v1"):
    return validate_and_normalize(graph, gid, ver)


def test_valid_graph() -> None:
    res, norm = _run(GOOD)
    assert res.schema_status == "valid"
    assert res.entity_count == 3
    assert res.relationship_count == 2
    assert res.duplicate_entities == 0
    assert res.dangling_relationships == 0
    assert res.normalized_graph_ref == "graphs/graph_contracts/v1"
    assert len(norm["entities"]) == 3 and len(norm["relationships"]) == 2


def test_dangling_relationship_rejected() -> None:
    bad = {
        "entities": [{"id": "a", "type": "X"}],
        "relationships": [{"source": "a", "type": "R", "target": "ghost"}],
    }
    res, norm = _run(bad)
    assert res.schema_status == "invalid"
    assert res.dangling_relationships == 1
    assert norm["relationships"] == []          # dropped from normalized graph
    assert any(i.code == "dangling_relationship" for i in res.issues)


def test_duplicate_entities_detected() -> None:
    dup = {
        "entities": [{"id": "a", "type": "X"}, {"id": "a", "type": "X"}],
        "relationships": [],
    }
    res, _ = _run(dup)
    assert res.duplicate_entities == 1
    assert res.entity_count == 1
    assert res.schema_status == "invalid"


def test_duplicate_relationships_collapsed() -> None:
    g = {
        "entities": [{"id": "a", "type": "X"}, {"id": "b", "type": "Y"}],
        "relationships": [
            {"source": "a", "type": "R", "target": "b"},
            {"source": "a", "type": "R", "target": "b"},
        ],
    }
    res, norm = _run(g)
    assert res.duplicate_relationships == 1
    assert res.relationship_count == 1
    assert len(norm["relationships"]) == 1


def test_empty_entities_is_invalid() -> None:
    res, _ = _run({"entities": [], "relationships": []})
    assert res.schema_status == "invalid"
    assert "entities" in res.empty_collections


def test_missing_id_or_type_rejected() -> None:
    g = {"entities": [{"id": "a"}, {"type": "X"}, {"id": "b", "type": "Y"}],
         "relationships": []}
    res, _ = _run(g)
    assert res.entity_count == 1              # only the valid one survives
    assert any(i.code == "invalid_entity" for i in res.issues)


def test_bad_schema_shape() -> None:
    res, _ = _run({"entities": "nope", "relationships": {}})
    assert res.schema_status == "invalid"
    assert any(i.code == "schema" for i in res.issues)


def test_properties_preserved() -> None:
    g = {
        "entities": [{"id": "a", "type": "X", "name": "Acme", "size": 10}],
        "relationships": [],
    }
    _, norm = _run(g)
    assert norm["entities"][0]["properties"] == {"name": "Acme", "size": 10}


def test_build_graph_json_is_order_independent() -> None:
    # Same data in different DB-row orders must produce identical JSON, so the
    # content hash is stable and dedup/idempotency holds (C05 hash fix).
    a = build_graph_json(
        [(2, "B", {}), (1, "A", {})],
        [(2, 1, "R"), (1, 2, "Q")],
    )
    b = build_graph_json(
        [(1, "A", {}), (2, "B", {})],
        [(1, 2, "Q"), (2, 1, "R")],
    )
    assert a == b
    import json
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_build_graph_json_from_rows() -> None:
    entities = [(1, "Customer", {"name": "Acme"}), (2, "Contract", {})]
    rels = [(1, 2, "HAS_CONTRACT")]
    g = build_graph_json(entities, rels)
    assert g["entities"][0] == {"id": "1", "type": "Customer", "properties": {"name": "Acme"}}
    assert g["relationships"][0] == {"source": "1", "type": "HAS_CONTRACT", "target": "2"}
    # And it validates clean.
    res, _ = validate_and_normalize(g, "graph_ws1", "v1")
    assert res.schema_status == "valid"
