"""Discovery orchestration: run one source end-to-end (extract -> land).

Top-level use case that wires a connector, the streaming spine, and the
landing store under a single tracked run. This is the seam where an external
orchestrator (cron / queue / API) hooks in.
"""
from __future__ import annotations

import logging

from aryx.connectors.base import Connector
from aryx.pipeline.run import run_spine
from aryx.store.batch_sink import BatchSink
from aryx.store.postgres_store import PostgresStore

logger = logging.getLogger(__name__)


def discover(
    connector: Connector,
    store: PostgresStore,
    system: str,
    dataset: str,
) -> int:
    """Land a source's cleaned records + profiles under one tracked run.

    Args:
        connector: Configured source connector.
        store: Open Postgres landing store.
        system: Source system label for the run.
        dataset: Source dataset/table label for the run.

    Returns:
        The run id, for downstream stages to reference.
    """
    run_id = store.start_run(system, dataset)
    sink = BatchSink(store, run_id)
    profiles = run_spine(connector, sink=sink)
    sink.flush()
    store.save_profiles(run_id, profiles)
    store.finish_run(run_id, sink.total)
    logger.info("discover complete run_id=%s records=%d", run_id, sink.total)
    return run_id
