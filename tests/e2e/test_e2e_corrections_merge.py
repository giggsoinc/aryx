"""Real-Postgres coverage for corrections_api.py's "merge" correction.

Raven-review gap: corrections_api.py's own entity-merge path had zero test
coverage at all, even though it's the OTHER caller of
repoint_relationships_safely (alongside adjudication_merge.py). Proves the
shared self-loop/dedupe fix actually applies here too, through the real
correction-application code path, not just the adjudication one.
"""
from __future__ import annotations

import psycopg
import pytest

pytestmark = pytest.mark.e2e


def _seed_entity(dsn: str, workspace_id: int, name: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO aryx_entity (workspace_id, ontology_type, "
                "attributes, confidence) VALUES (%s, 'Company', %s, 1) "
                "RETURNING id",
                (workspace_id, psycopg.types.json.Json({"name": name})))
            return cur.fetchone()[0]


def _add_relationship(dsn: str, workspace_id: int, src: int, tgt: int, name: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO aryx_relationship (workspace_id, source_entity_id, "
                "target_entity_id, name, confidence) VALUES (%s, %s, %s, %s, 1)",
                (workspace_id, src, tgt, name))


def _relationships(dsn: str, workspace_id: int) -> list[tuple[int, int, str]]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_entity_id, target_entity_id, name "
                "FROM aryx_relationship WHERE workspace_id = %s", (workspace_id,))
            return cur.fetchall()


def test_merge_correction_dedupes_edge_to_a_shared_third_entity(workspace, e2e_dsn) -> None:
    """The same dedupe case reproduced against corrections_api's merge
    branch directly (not adjudication's): entity_id absorbed into
    target_id must not leave a duplicate edge to a shared third entity."""
    from aryx.api.corrections_api import CorrectionRequest, _apply_correction

    wid = workspace["id"]
    keep = _seed_entity(e2e_dsn, wid, "Asha L.")
    drop = _seed_entity(e2e_dsn, wid, "Asha Labs")
    third = _seed_entity(e2e_dsn, wid, "Tech Sector")

    _add_relationship(e2e_dsn, wid, keep, third, "INDUSTRY")
    _add_relationship(e2e_dsn, wid, drop, third, "INDUSTRY")

    result = _apply_correction(
        wid, CorrectionRequest(kind="merge", entity_id=drop, target_id=keep))

    assert result["kind"] == "alias"
    rels = [r for r in _relationships(e2e_dsn, wid) if r[2] == "INDUSTRY"]
    assert rels == [(keep, third, "INDUSTRY")], (
        "merge correction must not leave a duplicate INDUSTRY edge behind")


def test_merge_correction_drops_a_self_loop_instead_of_creating_one(workspace, e2e_dsn) -> None:
    """Same self-loop case reproduced against corrections_api's merge
    branch: a direct pre-existing edge between the absorbed and surviving
    entities must be dropped, not turned into a self-loop."""
    from aryx.api.corrections_api import CorrectionRequest, _apply_correction

    wid = workspace["id"]
    keep = _seed_entity(e2e_dsn, wid, "Asha L.")
    drop = _seed_entity(e2e_dsn, wid, "Asha Labs")
    _add_relationship(e2e_dsn, wid, drop, keep, "DUP_OF")

    _apply_correction(
        wid, CorrectionRequest(kind="merge", entity_id=drop, target_id=keep))

    rels = _relationships(e2e_dsn, wid)
    assert not any(src == tgt for src, tgt, _ in rels), (
        "no self-loop should survive a merge correction")
