"""In-memory store of document-discovery results awaiting user confirmation.

The read step extracts mentions and stashes them here keyed by a discovery id;
the confirm step retrieves and ingests the user-approved subset. Process memory
only — nothing is written to disk.
"""
from __future__ import annotations

from typing import Any

_STORE: dict[str, dict[str, Any]] = {}


def put(discovery_id: str, data: dict[str, Any]) -> None:
    """Store a discovery result."""
    _STORE[discovery_id] = data


def get(discovery_id: str) -> dict[str, Any] | None:
    """Return a discovery result, or None if unknown/expired."""
    return _STORE.get(discovery_id)


def drop(discovery_id: str) -> None:
    """Forget a discovery result."""
    _STORE.pop(discovery_id, None)
