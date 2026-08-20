"""Shared fixtures for cross-component (e2e) tests — real Postgres + FalkorDB,
no mocked stores. See docs/plan_dashboard_mcp_tools.md's sibling test plan
for why these exist: unit tests mock every store, so nothing today asserts a
chain survives start-to-finish against real infra.

Requires a live stack (`docker compose up -d` locally, or the e2e CI job's
service containers) reachable at the URLs below. LLM calls are stubbed per
test (see `fake_complete_json`) — real inference is slow/non-deterministic
and orthogonal to what these tests check: whether components hand off to
each other correctly, not model quality.
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
# from the environment — any code called in-process (e.g. aryx.mcp.act,
# which never goes over HTTP) must see the same DSN/graph_url as the
# fixtures below, not Settings' in-container-port defaults.
os.environ.setdefault("ARYX_RDB_DSN", _DSN)
os.environ.setdefault("ARYX_GRAPH_URL", _GRAPH_URL)
# Settings.blob_dir defaults to /data/aryx-blobs (a container-only path) —
# on the host running these tests, that's a read-only root. Use a real
# writable temp dir instead.
os.environ.setdefault("ARYX_BLOB_DIR", os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "aryx-e2e-blobs"))


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
    """A fresh, isolated workspace — created before the test, deleted after.

    Yields the workspace dict ({"id": ..., "name": ..., ...}) rather than
    just the id, since some chains (e.g. auto-chain) need the brief/context
    fields too.
    """
    from aryx.workspaces import WorkspaceStore
    store = WorkspaceStore(e2e_dsn)
    ws = store.create(f"e2e_{uuid.uuid4().hex[:10]}")
    try:
        yield ws
    finally:
        store.delete(ws["id"])
        store.close()


def fake_complete_json(dataset_id: str = "", kpi_id: str = "k1",
                       analysis_id: str = "a1", chart_id: str = "c1") -> Any:
    """A deterministic stand-in for aryx.llm.complete_json's signature
    (broker, tier, system, user, schema) -> dict. Ignores the prompt
    entirely and returns a minimal, schema-shaped candidate — these tests
    check that a real response flows correctly through grounding/
    validation/execution, not that the model produced a *good* one.

    Pass dataset_id for workspace-scope planning (run_planner_workspace) —
    each kpi/analysis needs it there; leave empty for single-dataset mode
    (run_planner), where it's expected empty.
    """
    def _fake(broker: Any, tier: str, system: str, user: str,
             schema: dict) -> dict:
        return {
            "business_questions": [{"question_id": "q1",
                                   "text": "How much did we spend by category?"}],
            "kpis": [{"kpi_id": kpi_id, "name": kpi_id, "operation": "count",
                     "dataset_id": dataset_id, "measure": "amount",
                     "source_columns": ["amount"]}],
            "analyses": [{"analysis_id": analysis_id, "operation": "count",
                         "group_by": ["category"], "metric": kpi_id,
                         "dataset_id": dataset_id}],
            "visualizations": [{"chart_id": chart_id, "chart_type": "bar",
                               "source_ref": analysis_id}],
            "business_questions": [],
            "assumptions": [],
        }
    return _fake
