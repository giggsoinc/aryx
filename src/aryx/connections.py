"""In-memory store of live DB connection URLs for the ingest flow.

URLs include credentials, so they are held in process memory only — never
written to disk or git (mirrors the runtime LLM-key pattern). V2 will resolve
connection secrets from a secrets manager instead.
"""
from __future__ import annotations

import uuid

_CONNECTIONS: dict[str, str] = {}


def put(url: str) -> str:
    """Store a connection URL and return an opaque id."""
    cid = uuid.uuid4().hex
    _CONNECTIONS[cid] = url
    return cid


def get(cid: str) -> str | None:
    """Return the URL for a connection id, or None if unknown/expired."""
    return _CONNECTIONS.get(cid)


def drop(cid: str) -> None:
    """Forget a connection."""
    _CONNECTIONS.pop(cid, None)
