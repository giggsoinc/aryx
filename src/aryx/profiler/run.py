"""Glue: profile a stored dataset snapshot and persist the result (C03).

Shared by the ingest auto-trigger, the backfill, and the API so the fetch →
profile → save flow lives in exactly one place.
"""
from __future__ import annotations

import logging

from aryx.profiler.models import DatasetProfile
from aryx.profiler.profile import profile_dataset
from aryx.store.dataset_store import DatasetStore
from aryx.store.profile_store import ProfileStore

logger = logging.getLogger(__name__)


def run_profile(dsn: str, workspace_id: int, dataset_id: str,
                version: str | None = None) -> DatasetProfile | None:
    """Fetch a version's immutable snapshot, profile it, and persist the profile.

    Args:
        version: Specific version, or None for the dataset's latest.

    Returns:
        The saved DatasetProfile, or None if the snapshot could not be found.
    """
    dstore = DatasetStore(dsn, workspace_id)
    try:
        ver = version or dstore.latest_version(dataset_id)
        if ver is None:
            return None
        raw = dstore.get_raw(dataset_id, ver)
    finally:
        dstore.close()
    if raw is None:
        return None
    data, fmt = raw
    profile = profile_dataset(data, fmt, dataset_id, ver)
    pstore = ProfileStore(dsn, workspace_id)
    try:
        pstore.save(profile)
    finally:
        pstore.close()
    logger.info("profiled dataset=%s version=%s cols=%d rows=%d",
                dataset_id, ver, profile.column_count, profile.row_count)
    return profile
