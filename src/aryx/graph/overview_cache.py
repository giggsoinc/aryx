"""Short-lived per-workspace cache for the Ask overview.

The overview (exact type counts, value breakdowns, sample names) is the same
for every question until the data changes, yet it costs several aggregate
queries. It is cached in this process for ``ARYX_ASK_OVERVIEW_TTL`` seconds and
dropped when the graph changes (``graph.changes.after_graph_change``), so a
fresh ingest shows up immediately in the process that ran it. Other API
processes pick it up when their entry expires. A TTL of 0 disables the cache.
"""
from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_entries: dict[int, tuple[float, Any]] = {}


def get(workspace_id: int, ttl: float) -> Any | None:
    """Return the cached value for the workspace, or None if absent or expired."""
    if ttl <= 0:
        return None
    with _lock:
        hit = _entries.get(int(workspace_id))
        if hit is None:
            return None
        if hit[0] <= time.monotonic():
            del _entries[int(workspace_id)]
            return None
        return hit[1]


def put(workspace_id: int, value: Any, ttl: float) -> None:
    """Store a value for ``ttl`` seconds (no-op when ttl <= 0)."""
    if ttl <= 0:
        return
    with _lock:
        _entries[int(workspace_id)] = (time.monotonic() + ttl, value)


def invalidate(workspace_id: int | None = None) -> None:
    """Drop one workspace's entry, or every entry when no id is given."""
    with _lock:
        if workspace_id is None:
            _entries.clear()
        else:
            _entries.pop(int(workspace_id), None)
