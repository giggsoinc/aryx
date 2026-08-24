"""AdjudicationStore against real Postgres: survivorship-routed merges,
list-level duplicate collapsing, and workspace-delete cleanup.

Regression coverage for bugs found via manual smoke testing this session:
(1) merge_entities_of used to keep the survivor's pre-existing attribute
values unconditionally, ignoring the workspace's configured
SurvivorshipPolicy entirely; (2) two adjudication rows that collapse to the
same entity pair (e.g. because a third pair auto-merged them mid-run) both
stayed visible in the pending list; (3) WorkspaceStore.delete() dropped the
partitioned tables (landed records, entities, ...) but never touched
aryx_adjudication — its rows aren't partitioned, so they silently survived
workspace deletion and resurfaced as "pending" cards pointing at nothing
once a later workspace happened to reuse the same numeric id.

No LLM involved — entities/records are seeded directly via SQL, so this
runs in CI (pytest.mark.e2e only, not e2e_llm).
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest

pytestmark = pytest.mark.e2e


@contextmanager
def _count_round_trips():
    """Count real SQL round trips (Cursor.execute calls) made inside the
    `with` block — the same technique used to manually measure this fix
    against live data (91 -> 2 round trips for a 45-pending-row workspace)
    before this test existed, now codified so a regression to a per-row
    loop fails CI instead of needing another manual measurement."""
    import psycopg

    counter = {"n": 0}
    original = psycopg.Cursor.execute

    def counting_execute(self, *args, **kwargs):
        counter["n"] += 1
        return original(self, *args, **kwargs)

    psycopg.Cursor.execute = counting_execute
    try:
        yield counter
    finally:
        psycopg.Cursor.execute = original


def _seed_entity(dsn: str, workspace_id: int, name: str,
                 cleaned_at: str = "2026-01-01") -> tuple[int, int]:
    """A minimal Company entity with one backing landed record.

    Returns (entity_id, landed_record_id).
    """
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO aryx_entity (workspace_id, ontology_type, "
                "attributes, confidence) VALUES (%s, 'Company', %s, 1) "
                "RETURNING id",
                (workspace_id, psycopg.types.json.Json({"name": name})))
            entity_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO aryx_run (workspace_id, source_system, "
                "source_dataset, status) VALUES (%s, 'test', 'test', 'done') "
                "RETURNING run_id",
                (workspace_id,))
            run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO aryx_landed_record (workspace_id, run_id, "
                "source_system, source_dataset, source_record_id, payload, "
                "cleaned_at) VALUES (%s, %s, 'test', 'test', %s, %s, %s) "
                "RETURNING id",
                (workspace_id, run_id, name,
                 psycopg.types.json.Json({"name": name}), cleaned_at))
            landed_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO aryx_entity_member (workspace_id, entity_id, "
                "landed_record_id, confidence) VALUES (%s, %s, %s, 1)",
                (workspace_id, entity_id, landed_id))
    return entity_id, landed_id


def test_merge_entities_of_honors_configured_survivorship_policy(workspace, e2e_dsn) -> None:
    """A "most_recent" policy must pick the newer contribution's value, not
    whichever entity happens to have the lower id."""
    from aryx.resolution.survivorship import SurvivorshipPolicy
    from aryx.store.adjudication_store import AdjudicationStore

    wid = workspace["id"]
    older_entity, older_record = _seed_entity(e2e_dsn, wid, "Asha L", "2026-01-01")
    newer_entity, newer_record = _seed_entity(e2e_dsn, wid, "Asha Labs", "2026-06-01")
    assert older_entity < newer_entity, "test assumes the OLDER name has the lower id"

    store = AdjudicationStore(e2e_dsn, wid)
    merged = store.merge_entities_of(
        older_record, newer_record,
        SurvivorshipPolicy(default_strategy="most_recent"))
    assert merged is True

    survivor = store.entity_of_record(older_record)
    assert survivor == older_entity, "lower id still keeps the row (storage detail only)"

    import psycopg
    with psycopg.connect(e2e_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT attributes FROM aryx_entity WHERE id = %s",
                       (survivor,))
            attrs = cur.fetchone()[0]
            cur.execute(
                "SELECT strategy, winning_value FROM aryx_attribute_conflict "
                "WHERE workspace_id = %s AND entity_id = %s", (wid, survivor))
            conflict = cur.fetchone()

    # The newer contribution's value wins the attribute — NOT the survivor's
    # own pre-existing value. This is the exact bug: before the fix, this
    # asserted "Asha L" (the survivor's original value) unconditionally.
    assert attrs["name"] == "Asha Labs"
    assert conflict == ("most_recent", "Asha Labs")


def test_page_collapses_pending_rows_for_the_same_entity_pair(workspace, e2e_dsn) -> None:
    """Two adjudication rows already resolving to the same two entities
    must show up once in the pending list, not twice."""
    from aryx.store.adjudication_store import AdjudicationStore

    wid = workspace["id"]
    entity_a, record_a = _seed_entity(e2e_dsn, wid, "Byte Ca")
    entity_b, record_b = _seed_entity(e2e_dsn, wid, "Byte Cafe")

    store = AdjudicationStore(e2e_dsn, wid)
    # Same underlying entity pair, offered twice — e.g. two different
    # record-level pairs that both happened to land on these two entities.
    id1 = store.enqueue(1, record_a, record_b, 0.86, 0.85,
                        "llm rescore below auto-merge threshold", "pending")
    id2 = store.enqueue(1, record_a, record_b, 0.80, None,
                        "llm unavailable — queued for human review", "pending")
    assert id1 != id2

    pending = store.page("pending")
    ids = [row["id"] for row in pending]
    assert id1 in ids
    assert id2 not in ids, "duplicate entity-pair row must be collapsed from the list"

    # Deciding the surviving row must still close the collapsed duplicate —
    # it isn't lost, just hidden from the list until acted on.
    from aryx.resolution.review_queue import apply_decision
    result = apply_decision(store, id1, approve=False, decided_by="e2e-test")
    assert result["duplicates_closed"] == [id2]


def test_workspace_delete_also_removes_adjudication_rows(e2e_dsn) -> None:
    """Deleting a workspace must not leave orphaned adjudication rows
    behind — aryx_adjudication isn't in WorkspaceStore's partitioned-table
    list, so it used to survive deletion forever and resurface as a
    "pending" card pointing at nothing once a later workspace reused the
    same numeric id."""
    import psycopg

    from aryx.store.adjudication_store import AdjudicationStore
    from aryx.workspaces import WorkspaceStore

    wstore = WorkspaceStore(e2e_dsn)
    ws = wstore.create(f"e2e_delete_{uuid.uuid4().hex[:8]}")
    wid = ws["id"]
    store = AdjudicationStore(e2e_dsn, wid)
    adj_id = store.enqueue(1, 111, 112, 0.5, None, None, "pending")

    def _count() -> int:
        with psycopg.connect(e2e_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM aryx_adjudication WHERE id = %s",
                           (adj_id,))
                return cur.fetchone()[0]

    assert _count() == 1
    wstore.delete(wid)
    wstore.close()
    assert _count() == 0, "adjudication row survived workspace delete"


def test_page_round_trip_count_does_not_scale_with_pending_rows(
    workspace, e2e_dsn,
) -> None:
    """AdjudicationStore.page() must cost a CONSTANT number of SQL round
    trips, not one that grows with the number of pending rows.

    Regression for the exact fix this session: page() used to call
    entity_of_record() twice per row (2 DB round trips each), so a real
    45-pending-row workspace cost 91 round trips just to render the list.
    _entities_of_records() batches that into one query. Proven here by
    comparing the round-trip count at 3 pending pairs vs 6 — if someone
    reintroduces a per-row loop, the count would double; it must not move
    at all.
    """
    from aryx.store.adjudication_store import AdjudicationStore

    wid = workspace["id"]
    store = AdjudicationStore(e2e_dsn, wid)

    def _seed_n_pairs(n: int) -> None:
        for i in range(n):
            _, record_a = _seed_entity(e2e_dsn, wid, f"Company A{i}")
            _, record_b = _seed_entity(e2e_dsn, wid, f"Company B{i}")
            store.enqueue(1, record_a, record_b, 0.6, None, None, "pending")

    _seed_n_pairs(3)
    with _count_round_trips() as counter:
        rows_at_3 = store.page("pending")
    round_trips_at_3 = counter["n"]
    assert len(rows_at_3) == 3

    _seed_n_pairs(3)  # now 6 pending rows total
    with _count_round_trips() as counter:
        rows_at_6 = store.page("pending")
    round_trips_at_6 = counter["n"]
    assert len(rows_at_6) == 6

    assert round_trips_at_6 == round_trips_at_3, (
        f"page() round trips grew with row count ({round_trips_at_3} -> "
        f"{round_trips_at_6}) — a per-row loop regressed back in")
    assert round_trips_at_3 <= 3, (
        "expected ~2 round trips (page fetch + one batched entity lookup), "
        f"got {round_trips_at_3}")


def test_pending_duplicates_of_round_trip_count_does_not_scale(
    workspace, e2e_dsn,
) -> None:
    """Same fix, same proof, for pending_duplicates_of() specifically —
    it does its own batched lookup across every OTHER pending row, which
    is the part most likely to regress independently of page()."""
    from aryx.store.adjudication_store import AdjudicationStore

    wid = workspace["id"]
    store = AdjudicationStore(e2e_dsn, wid)
    _, record_a = _seed_entity(e2e_dsn, wid, "Anchor Co")
    _, record_b = _seed_entity(e2e_dsn, wid, "Anchor Corp")
    anchor_id = store.enqueue(1, record_a, record_b, 0.6, None, None, "pending")

    def _seed_noise(n: int) -> None:
        for i in range(n):
            _, r1 = _seed_entity(e2e_dsn, wid, f"Noise A{i}")
            _, r2 = _seed_entity(e2e_dsn, wid, f"Noise B{i}")
            store.enqueue(1, r1, r2, 0.6, None, None, "pending")

    _seed_noise(3)
    with _count_round_trips() as counter:
        store.pending_duplicates_of(anchor_id, record_a, record_b)
    round_trips_at_3 = counter["n"]

    _seed_noise(3)  # 6 other pending rows now
    with _count_round_trips() as counter:
        store.pending_duplicates_of(anchor_id, record_a, record_b)
    round_trips_at_6 = counter["n"]

    assert round_trips_at_6 == round_trips_at_3, (
        f"pending_duplicates_of() round trips grew with row count "
        f"({round_trips_at_3} -> {round_trips_at_6}) — a per-row loop regressed back in")
    assert round_trips_at_3 <= 3
