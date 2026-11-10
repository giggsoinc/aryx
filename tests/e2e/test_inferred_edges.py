"""The reasoning engine on Postgres: closures, protection, rollback, reads.

Replaces the old Cypher-capturing unit tests. Everything runs against a real
database, because the closures ARE SQL — a mock could not catch a wrong join.
"""
from __future__ import annotations

from typing import Any

import pytest

from aryx.graph.pg_reader import PostgresGraphReader
from aryx.models import Relationship, ResolvedEntity
from aryx.reasoning.engine import evaluate_workspace
from aryx.store.entity_store import EntityStore
from aryx.store.inferred_store import InferredStore
from aryx.store.rule_store import RuleStore

pytestmark = pytest.mark.e2e


def _build(dsn: str, ws: int) -> dict[str, int]:
    """Entities and asserted edges used by every test; returns key -> id."""
    rows: list[tuple[str, str, dict[str, Any]]] = [
        ("p1", "Person", {"name": "Pat", "revenue": 5000}),
        ("p2", "Person", {"name": "Quinn", "revenue": 10}),
        ("co", "Company", {"name": "Acme"}),
        ("f1", "Person", {"name": "Fran"}),
        ("f2", "Person", {"name": "Gus"}),
        ("selfy", "Person", {"name": "Solo"}),
        ("platinum", "Tier", {"name": "Platinum"}),
        ("platinum2", "Tier", {"name": "Platinum"}),
    ]
    rows += [(f"n{i}", "Node", {"name": f"n{i}"}) for i in range(1, 7)]
    rows += [(f"c{i}", "Node", {"name": f"c{i}"}) for i in range(1, 4)]
    estore = EntityStore(dsn, ws)
    estore.save([(ResolvedEntity(ontology_type=t, attributes=a, confidence=1.0), [])
                 for _, t, a in rows])
    ids_sorted = sorted(r[0] for r in estore.list_entities())
    ids = {rows[n][0]: ids_sorted[n] for n in range(len(rows))}

    def edge(a: str, b: str, name: str) -> Relationship:
        return Relationship(source_entity_id=ids[a], target_entity_id=ids[b],
                            name=name, confidence=1.0)

    edges = [edge("p1", "co", "works_for"), edge("p2", "co", "works_for"),
             edge("f1", "f2", "friend"), edge("selfy", "selfy", "friend")]
    edges += [edge(f"n{i}", f"n{i + 1}", "part_of") for i in range(1, 6)]
    edges += [edge("c1", "c2", "tr"), edge("c2", "c3", "tr"), edge("c3", "c1", "tr")]
    estore.save_relationships(edges)
    return ids


@pytest.fixture
def world(e2e_dsn: str, workspace: dict) -> dict[str, Any]:
    ws = workspace["id"]
    return {"dsn": e2e_dsn, "ws": ws, "ids": _build(e2e_dsn, ws)}


def _inferred(dsn: str, ws: int) -> set[tuple[int, int, str]]:
    import psycopg
    with psycopg.connect(dsn, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT source_entity_id, target_entity_id, name"
            " FROM aryx_inferred_relationship WHERE workspace_id = %s", (ws,)).fetchall()
    return {(r[0], r[1], r[2]) for r in rows}


def test_inverse_creates_reversed_edges(world: dict) -> None:
    ids, dsn, ws = world["ids"], world["dsn"], world["ws"]
    with InferredStore(dsn, ws) as s:
        assert s.apply_inverse("works_for", "employs", "r") == 2
    assert _inferred(dsn, ws) == {(ids["co"], ids["p1"], "employs"),
                                  (ids["co"], ids["p2"], "employs")}


def test_inverse_never_relabels_an_asserted_edge(world: dict) -> None:
    from aryx.models import Relationship
    ids, dsn, ws = world["ids"], world["dsn"], world["ws"]
    EntityStore(dsn, ws).save_relationships([Relationship(
        source_entity_id=ids["co"], target_entity_id=ids["p1"],
        name="employs", confidence=1.0)])
    with InferredStore(dsn, ws) as s:
        assert s.apply_inverse("works_for", "employs") == 1  # only p2's
    assert (ids["co"], ids["p1"], "employs") not in _inferred(dsn, ws)


def test_symmetric_skips_self_loops_and_is_idempotent(world: dict) -> None:
    ids, dsn, ws = world["ids"], world["dsn"], world["ws"]
    with InferredStore(dsn, ws) as s:
        assert s.apply_symmetric("friend") == 1
        assert s.apply_symmetric("friend") == 0  # nothing new the second time
    assert _inferred(dsn, ws) == {(ids["f2"], ids["f1"], "friend")}


@pytest.mark.parametrize("depth,expected", [(2, 4), (3, 7), (4, 9), (10, 9)])
def test_transitive_chain_counts_by_depth(world: dict, depth: int, expected: int) -> None:
    dsn, ws = world["dsn"], world["ws"]
    with InferredStore(dsn, ws) as s:
        assert s.apply_transitive("part_of", depth) == expected  # 10 is capped at 4


def test_transitive_over_a_cycle_connects_distinct_endpoints_only(world: dict) -> None:
    ids, dsn, ws = world["ids"], world["dsn"], world["ws"]
    with InferredStore(dsn, ws) as s:
        s.apply_transitive("tr", 4)
    got = _inferred(dsn, ws)
    assert got == {(ids["c1"], ids["c3"], "tr"), (ids["c2"], ids["c1"], "tr"),
                   (ids["c3"], ids["c2"], "tr")}
    assert not any(a == b for a, b, _ in got)


def test_named_target_edge_hits_every_match_and_none_when_unknown(world: dict) -> None:
    ids, dsn, ws = world["ids"], world["dsn"], world["ws"]
    with InferredStore(dsn, ws) as s:
        assert s.add_named_target_edge(ids["p1"], "INF_TIER", "Tier", "Platinum") == 2
        assert s.add_named_target_edge(ids["p1"], "INF_TIER", "Tier", "Nope") == 0
        assert s.add_named_target_edge(ids["p1"], "INF_TIER", "Company", "Platinum") == 0


def test_set_label_replaces(world: dict) -> None:
    ids, dsn, ws = world["ids"], world["dsn"], world["ws"]
    with InferredStore(dsn, ws) as s:
        s.set_label(ids["p1"], "Gold", "r1")
        s.set_label(ids["p1"], "Platinum", "r2")
    assert PostgresGraphReader(dsn, ws).get_entity(ids["p1"])["inferred_label"] == "Platinum"


def test_a_failed_evaluation_rolls_back_cleanly(world: dict) -> None:
    ids, dsn, ws = world["ids"], world["dsn"], world["ws"]
    with InferredStore(dsn, ws) as s:
        s.apply_symmetric("friend")
    with pytest.raises(RuntimeError):
        with InferredStore(dsn, ws) as s:
            s.clear()
            s.apply_inverse("works_for", "employs")
            raise RuntimeError("boom")
    # the earlier output survived; nothing half-built was kept
    assert _inferred(dsn, ws) == {(ids["f2"], ids["f1"], "friend")}


def test_reader_surfaces_inferred_edges_and_labels(world: dict) -> None:
    ids, dsn, ws = world["ids"], world["dsn"], world["ws"]
    with InferredStore(dsn, ws) as s:
        s.apply_inverse("works_for", "employs")
        s.apply_transitive("part_of", 2)
        s.set_label(ids["p1"], "Gold")
    reader = PostgresGraphReader(dsn, ws)
    inferred = [n for n in reader.neighbors(ids["co"]) if n.get("inferred")]
    assert {n["name"] for n in inferred} == {"Pat", "Quinn"}
    assert all(n["relationship"] == "employs" and n["direction"] == "out" for n in inferred)
    assert {(n["relationship"], n.get("inferred", False))
            for n in reader.neighbors(ids["p1"])} == {
        ("works_for", False), ("employs", True)}  # asserted stays unflagged
    assert any(e.get("inferred") and e["name"] == "part_of"
               for e in reader.all_relationships())
    assert reader.count_by_relationship("Company", "employs", "Person") == {
        "Pat": 1, "Quinn": 1}
    assert reader.get_entity(ids["p1"])["inferred_label"] == "Gold"
    # an inferred shortcut shortens a path
    assert [s["id"] for s in reader.shortest_path(ids["n1"], ids["n3"], 1)] == [
        ids["n1"], ids["n3"]]


def test_evaluate_workspace_runs_entity_and_edge_rules(world: dict) -> None:
    """Entity rules used to crash on tuples; edge rules on a missing run()."""
    ids, dsn, ws = world["ids"], world["dsn"], world["ws"]
    rules = RuleStore(dsn)
    rules.upsert(ws, "gold", {"type": "Person", "attr": "revenue", "op": ">", "value": 1000},
                 {"set_label": "Gold"})
    rules.upsert(ws, "tier", {"type": "Person", "attr": "revenue", "op": ">", "value": 1000},
                 {"add_relationship": "tier_member", "target_type": "Company",
                  "target_name": "Acme"})
    rules.upsert(ws, "inv", {"edge": "works_for"}, {"inverse_of": "employs"})
    result = evaluate_workspace(ws)
    assert result["rules_evaluated"] == 3
    assert result["per_rule"] == {"gold": 1, "tier": 1, "inv": 1}
    reader = PostgresGraphReader(dsn, ws)
    assert reader.get_entity(ids["p1"])["inferred_label"] == "Gold"
    assert "inferred_label" not in reader.get_entity(ids["p2"])
    assert (ids["p1"], ids["co"], "INF_TIER_MEMBER") in _inferred(dsn, ws)
    # re-running is idempotent, and deleting every rule clears the output
    assert evaluate_workspace(ws)["per_rule"] == result["per_rule"]
    for name in ("gold", "tier", "inv"):
        rules.delete(ws, name)
    assert evaluate_workspace(ws) == {"rules_evaluated": 0, "total_fires": 0, "per_rule": {}}
    assert _inferred(dsn, ws) == set()
    assert "inferred_label" not in reader.get_entity(ids["p1"])
