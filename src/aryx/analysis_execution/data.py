"""Load real, typed rows for one dataset — the raw C02 snapshot re-parsed
and converted with the EXACT SAME policy C10 already logged, so C12 executes
against the same values C10's transformation log describes rather than a
second, possibly-divergent conversion pass.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.andie_planner.models import DashboardSpec
from aryx.preprocess.policy import derive_conversion_policy, referenced_columns
from aryx.preprocess.transform import convert_column
from aryx.profiler.profile import _load
from aryx.store.dataset_store import DatasetStore
from aryx.store.profile_store import ProfileStore

logger = logging.getLogger(__name__)


def load_typed_rows(dsn: str, workspace_id: int, dataset_id: str,
                    spec: DashboardSpec, row_limit: int) -> tuple[list[dict[str, Any]], str]:
    """Return (typed rows, dataset_version) for one dataset, bounded to
    `row_limit` rows. Empty list (version "") if the raw snapshot or its
    profile is unavailable — best-effort, same contract as C10.
    """
    pstore = ProfileStore(dsn, workspace_id)
    try:
        profile = pstore.latest(dataset_id)
    finally:
        pstore.close()
    if profile is None:
        return [], ""

    dstore = DatasetStore(dsn, workspace_id)
    try:
        raw = dstore.get_raw(dataset_id, profile.dataset_version)
    finally:
        dstore.close()
    if raw is None:
        return [], profile.dataset_version

    data, fmt = raw
    rows, _order = _load(data, fmt)
    if row_limit > 0:
        rows = rows[:row_limit]

    columns = referenced_columns(spec, dataset_id)
    conversion_policy = derive_conversion_policy(profile, columns)
    for column, operation in conversion_policy.items():
        values = [r.get(column) for r in rows]
        converted, _failed, _changed, _reverted = convert_column(values, operation)
        for row, value in zip(rows, converted):
            row[column] = value
    return rows, profile.dataset_version
