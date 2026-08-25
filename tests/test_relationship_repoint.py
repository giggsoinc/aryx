"""Unit coverage for repoint_relationships_safely's call sequence.

Raven-review gap: the shared helper (self-loop delete -> duplicate delete
-> repoint) only had e2e coverage. This pins the exact query order and
parameter shape with a mocked cursor, so a regression in call order or
param wiring fails fast without needing Postgres.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

from aryx.queries import load
from aryx.store.relationship_repoint import repoint_relationships_safely


def test_runs_self_loop_delete_then_dedupe_then_repoint_in_order() -> None:
    cur = MagicMock()

    repoint_relationships_safely(cur, workspace_id=7, drop=20, keep=10)

    assert cur.execute.call_args_list == [
        call(load("delete_relationship_self_loops_on_merge"), (7, 20, 10, 10, 20)),
        call(load("delete_relationship_duplicates_before_repoint"), (7, 20, 10, 20, 10)),
        call(load("repoint_relationships"), (20, 10, 20, 10, 7, 20, 20)),
    ]


def test_runs_exactly_three_statements() -> None:
    """No extra queries, no fewer — a silently-dropped cleanup step would
    reintroduce the exact bug this helper exists to fix."""
    cur = MagicMock()

    repoint_relationships_safely(cur, workspace_id=1, drop=2, keep=3)

    assert cur.execute.call_count == 3
