"""Tests for the Knowledge Graph Profiler (C06) — pure, no DB, no LLM."""
from __future__ import annotations

from aryx.graph_profiler import profile_graph

# A small contracts graph: Customer -HAS_CONTRACT-> Contract -MANAGED_BY->
# AccountManager -ASSIGNED_TO_REGION-> Region.
NORMALIZED = {
    "entities": [
        {"id": "cu1", "type": "Customer"}, {"id": "cu2", "type": "Customer"},
        {"id": "c1", "type": "Contract"}, {"id": "c2", "type": "Contract"},
        {"id": "m1", "type": "AccountManager"},
        {"id": "r1", "type": "Region"},
        {"id": "iso1", "type": "Orphan"},          # disconnected type
    ],
    "relationships": [
        {"source": "cu1", "type": "HAS_CONTRACT", "target": "c1"},
        {"source": "cu2", "type": "HAS_CONTRACT", "target": "c2"},
        {"source": "c1", "type": "MANAGED_BY", "target": "m1"},
        {"source": "c2", "type": "MANAGED_BY", "target": "m1"},
        {"source": "m1", "type": "ASSIGNED_TO_REGION", "target": "r1"},
    ],
}


def _profile(**kw):
    return profile_graph(NORMALIZED, "graph_contracts", "v1", **kw)


def test_ids_and_counts() -> None:
    p = _profile()
    assert p.graph_profile_id == "graph_profile_graph_contracts_v1"
    assert p.entity_count == 7
    assert p.relationship_count == 5
    counts = {t.type: t.count for t in p.entity_types}
    assert counts["Customer"] == 2 and counts["Contract"] == 2
    assert p.profile_status == "valid"


def test_relationship_types_and_schema_edges() -> None:
    p = _profile()
    rtypes = {t.type: t.count for t in p.relationship_types}
    assert rtypes["HAS_CONTRACT"] == 2 and rtypes["MANAGED_BY"] == 2
    edges = {(e.source_type, e.relationship, e.target_type) for e in p.schema_edges}
    assert ("Contract", "MANAGED_BY", "AccountManager") in edges
    assert ("AccountManager", "ASSIGNED_TO_REGION", "Region") in edges


def test_verified_path_contract_manager_region() -> None:
    p = _profile(max_depth=3)
    paths = {tuple(vp.path) for vp in p.verified_paths}
    assert ("Contract", "MANAGED_BY", "AccountManager",
            "ASSIGNED_TO_REGION", "Region") in paths
    vp = next(v for v in p.verified_paths
              if v.path == ["Contract", "MANAGED_BY", "AccountManager",
                            "ASSIGNED_TO_REGION", "Region"])
    assert vp.depth == 2
    # path_id includes relationship names (not just types) so it is unique.
    assert vp.path_id == "path_contract_managedby_accountmanager_assignedtoregion_region"


def test_path_ids_are_unique_across_same_type_sequence() -> None:
    # Two edges with the same types but different relationships must not collide.
    normalized = {
        "entities": [{"id": "a", "type": "A"}, {"id": "b", "type": "B"}],
        "relationships": [
            {"source": "a", "type": "owns", "target": "b"},
            {"source": "a", "type": "likes", "target": "b"},
        ],
    }
    p = profile_graph(normalized, "g", "v1")
    ids = [vp.path_id for vp in p.verified_paths]
    assert len(ids) == len(set(ids))          # no duplicate ids
    assert "path_a_owns_b" in ids and "path_a_likes_b" in ids


def test_self_loop_path_is_verified() -> None:
    normalized = {
        "entities": [{"id": "e1", "type": "Employee"}, {"id": "e2", "type": "Employee"}],
        "relationships": [{"source": "e1", "type": "REPORTS_TO", "target": "e2"}],
    }
    p = profile_graph(normalized, "g", "v1")
    # Employee -REPORTS_TO-> Employee is a real self-referential schema edge.
    assert any(vp.path == ["Employee", "REPORTS_TO", "Employee"] for vp in p.verified_paths)


def test_paths_are_bounded_by_depth() -> None:
    p = _profile(max_depth=1)
    assert all(vp.depth <= 1 for vp in p.verified_paths)
    # depth-1 edges exist
    assert any(vp.depth == 1 for vp in p.verified_paths)
    # the 2-hop path must NOT appear at depth 1
    assert all(len(vp.path) <= 3 for vp in p.verified_paths)


def test_no_invented_paths() -> None:
    # Every path's hops must correspond to a real schema edge.
    p = _profile(max_depth=3)
    schema = {(e.source_type, e.relationship, e.target_type) for e in p.schema_edges}
    for vp in p.verified_paths:
        for i in range(0, len(vp.path) - 2, 2):
            assert (vp.path[i], vp.path[i + 1], vp.path[i + 2]) in schema


def test_disconnected_type_flagged() -> None:
    p = _profile()
    assert any(f.code == "disconnected_type" and f.type == "Orphan"
               for f in p.quality_flags)


def test_objective_prioritizes_relevant_paths() -> None:
    p = _profile(user_objective="analyze region assignments")
    # A path touching Region should sort to the front.
    assert p.verified_paths
    assert any("Region" in vp.path for vp in p.verified_paths[:3])


def test_invalid_graph_marks_profile_invalid() -> None:
    p = _profile(graph_valid=False)
    assert p.profile_status == "invalid"
    assert any("validation" in lim for lim in p.limitations)
