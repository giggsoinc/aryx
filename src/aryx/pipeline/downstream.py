"""Shared C03-C07 downstream pipeline, gated on C01 (user intent) being valid.

Two call sites:
  - file_ingest_api._run_files, right after a dataset snapshot (C02) lands,
    if intent is already valid for the workspace.
  - intent_api.capture, right after intent turns valid, to backfill every
    dataset already sitting in the workspace unprofiled.

Every step is best-effort — one failure never blocks the rest, matching the
ingest pipeline's existing discipline.
"""
from __future__ import annotations

import logging

from aryx.graph_intake.run import run_intake
from aryx.graph_profiler.run import run_graph_profile
from aryx.planning.run import run_context, run_workspace_context
from aryx.profiler.run import run_profile
from aryx.semantic.run import run_interpret
from aryx.store.intent_store import IntentStore

logger = logging.getLogger(__name__)


def intent_ready(dsn: str, workspace_id: int) -> bool:
    """True once at least one valid C01 intent capture exists for the workspace."""
    store = IntentStore(dsn, workspace_id)
    try:
        return store.has_valid_intent()
    finally:
        store.close()


def run_downstream(dsn: str, workspace_id: int, dataset_ids: set[str] | list[str],
                   broker=None) -> None:
    """Run C03-C07 for the given datasets. Caller must check intent_ready() first."""
    ids = sorted(set(dataset_ids))
    for did in ids:
        try:
            run_profile(dsn, workspace_id, did)
        except Exception:  # noqa: BLE001 — profiling is additive, never block
            logger.warning("dataset profiling failed dataset=%s", did, exc_info=True)
        try:
            run_interpret(dsn, workspace_id, did, broker=broker)
        except Exception:  # noqa: BLE001 — interpretation is additive, never block
            logger.warning("semantic interpretation failed dataset=%s", did, exc_info=True)

    try:
        run_intake(dsn, workspace_id)
    except Exception:  # noqa: BLE001 — graph intake is additive, never block
        logger.warning("graph intake failed ws=%s", workspace_id, exc_info=True)
    try:
        run_graph_profile(dsn, workspace_id)
    except Exception:  # noqa: BLE001 — graph profile is additive, never block
        logger.warning("graph profile failed ws=%s", workspace_id, exc_info=True)

    for did in ids:
        try:
            run_context(dsn, workspace_id, did)
        except Exception:  # noqa: BLE001 — context is additive, never block
            logger.warning("planning context failed ws=%s dataset=%s",
                           workspace_id, did, exc_info=True)
    try:
        run_workspace_context(dsn, workspace_id)
    except Exception:  # noqa: BLE001 — context is additive, never block
        logger.warning("workspace planning context failed ws=%s", workspace_id,
                       exc_info=True)
