"""Batch runner wiring extract -> clean -> profile (stages 1-3).

Streams records one at a time: a record is cleaned, handed to an optional
sink, folded into the profile, then released. Nothing holds the full dataset,
so the same code path that serves a small table also survives a terabyte
(slower, not crashing). Parallel partitioned workers are deferred machinery.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from aryx.connectors.base import Connector
from aryx.models import CleanRecord, FieldProfile
from aryx.pipeline.clean import clean
from aryx.pipeline.profile import ProfileAccumulator

logger = logging.getLogger(__name__)

# A sink persists each cleaned record (e.g. to the RDB landing zone). The
# concrete batch-writing sink arrives in Increment 2; None means profile-only.
RecordSink = Callable[[CleanRecord], None]


def run_spine(
    connector: Connector,
    sink: RecordSink | None = None,
    log_every: int = 10_000,
) -> list[FieldProfile]:
    """Stream a source through clean + profile without materializing it.

    Args:
        connector: A configured source connector.
        sink: Optional callback to persist each cleaned record.
        log_every: Emit a progress line every N records.

    Returns:
        Per-field profiles for the extracted batch.
    """
    accumulator = ProfileAccumulator()
    count = 0
    for raw in connector.extract():
        record = clean(raw)
        accumulator.add(record)
        if sink is not None:
            sink(record)
        count += 1
        if count % log_every == 0:
            logger.info("spine progress records=%d", count)
    logger.info("spine complete records=%d", count)
    return accumulator.result()
