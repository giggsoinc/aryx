"""Shared fixtures for cross-component (e2e) tests — real Postgres + FalkorDB,
no mocked stores. Unit tests mock every store, so nothing else asserts a
chain survives start-to-finish against real infra.

Requires a live stack (`docker compose up -d` locally) reachable at the URLs
below.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

os.environ.setdefault("ARYX_API_URL", os.environ.get(
    "ARYX_TEST_API_URL", "http://localhost:8088"))

_DSN = os.environ.get("ARYX_TEST_RDB_DSN",
                      "postgresql://aryx:aryx@localhost:55432/aryx")
_GRAPH_URL = os.environ.get("ARYX_TEST_GRAPH_URL", "redis://localhost:6379")

# aryx.config.get_settings() is process-wide (@lru_cache) and reads these
# from the environment — any code called in-process must see the same
# DSN/graph_url as the fixtures below, not Settings' in-container defaults.
os.environ.setdefault("ARYX_RDB_DSN", _DSN)
os.environ.setdefault("ARYX_GRAPH_URL", _GRAPH_URL)


@pytest.fixture(scope="session")
def e2e_dsn() -> str:
    """Real Postgres DSN, migrated once per test session."""
    from aryx.store.migrate import apply_migrations
    apply_migrations(_DSN)
    return _DSN


@pytest.fixture(scope="session")
def e2e_graph_url() -> str:
    """Real FalkorDB connection URL."""
    return _GRAPH_URL


@pytest.fixture
def workspace(e2e_dsn: str) -> Any:
    """A fresh, isolated workspace — created before the test, deleted after."""
    from aryx.workspaces import WorkspaceStore
    store = WorkspaceStore(e2e_dsn)
    ws = store.create(f"e2e_{uuid.uuid4().hex[:10]}")
    try:
        yield ws
    finally:
        store.delete(ws["id"])
        store.close()
