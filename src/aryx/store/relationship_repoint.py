"""Safely repoint relationship edges when one entity absorbs another.

Shared by ``adjudication_merge.py`` (adjudication-approved merges) and
``corrections_api.py`` (manual "merge" corrections) — both delete a losing
entity and need its relationship edges to survive by pointing at the
keeper instead of dangling on a row that's about to disappear.
"""
from __future__ import annotations

from typing import Any

from aryx.queries import load


def repoint_relationships_safely(cur: Any, workspace_id: int,
                                 drop: int, keep: int) -> None:
    """Repoint ``drop``'s relationship edges onto ``keep``, cleanly.

    Two edge cases a plain repoint would otherwise leave behind (raven-review
    finding on PR #46's follow-up): a direct edge BETWEEN the two merging
    entities would become a self-loop ("keep relates to keep") once repointed
    — those are deleted outright, they carry no information once the two
    sides are the same entity. And if ``drop`` and ``keep`` already relate to
    some third entity the same way, repointing would create an exact
    duplicate row — the ``drop``-anchored copy is deleted first, keeping the
    original. Both cleanup passes run before the repoint itself, in the
    caller's existing transaction.
    """
    cur.execute(load("delete_relationship_self_loops_on_merge"),
                (workspace_id, drop, keep, keep, drop))
    cur.execute(load("delete_relationship_duplicates_before_repoint"),
                (workspace_id, drop, keep, drop, keep))
    cur.execute(load("repoint_relationships"),
                (drop, keep, drop, keep, workspace_id, drop, drop))
