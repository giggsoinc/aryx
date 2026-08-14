"""Glue: run C10 for one dataset referenced by an APPROVED spec (C09 output).

Chained onto C09's approval inside andie_planner/run.py — not a separate
trigger. Loads the C02 raw snapshot (read-only, never mutated), derives
conversion/null policy from C03's profile, transforms only the columns the
spec references, and persists the transformation log.
"""
from __future__ import annotations

import logging

from aryx.andie_planner.models import DashboardSpec
from aryx.preprocess.models import AnalysisDataset, TransformationEntry
from aryx.preprocess.policy import derive_conversion_policy, derive_null_policy, referenced_columns
from aryx.preprocess.transform import convert_column
from aryx.profiler.models import DatasetProfile
from aryx.profiler.profile import _load
from aryx.store.analysis_dataset_store import AnalysisDatasetStore
from aryx.store.dataset_store import DatasetStore

logger = logging.getLogger(__name__)


def run_preprocess(dsn: str, workspace_id: int, dataset_id: str,
                   spec: DashboardSpec, profile: DatasetProfile) -> AnalysisDataset | None:
    """Build, persist, and return the C10 transformation log for `dataset_id`.

    Returns None if the raw snapshot for `profile.dataset_version` can't be
    found (best-effort — C10 is additive, never blocks the spec result).
    """
    dstore = DatasetStore(dsn, workspace_id)
    try:
        raw = dstore.get_raw(dataset_id, profile.dataset_version)
    finally:
        dstore.close()
    if raw is None:
        return None
    data, fmt = raw
    rows, _order = _load(data, fmt)
    row_count = len(rows)

    columns = referenced_columns(spec, dataset_id)
    conversion_policy = derive_conversion_policy(profile, columns)
    # null_policy is derived for lineage/audit completeness (which columns
    # exclude nulls from a downstream aggregate) — C10 itself never drops
    # rows; enforcing the exclusion is a future compute stage's concern.
    derive_null_policy(spec, columns, dataset_id)

    transformations: list[TransformationEntry] = []
    quality_summary: dict[str, int] = {}
    any_reverted = False
    for column, operation in sorted(conversion_policy.items()):
        values = [r.get(column) for r in rows]
        _converted, failed, changed, reverted = convert_column(values, operation)
        transformations.append(TransformationEntry(
            column=column, operation=operation,
            failed_rows=failed, changed_rows=changed, reverted=reverted))
        null_count = sum(1 for v in values if v is None or str(v).strip() == "")
        quality_summary[f"{column}_null_rows"] = null_count
        if reverted:
            any_reverted = True
            quality_summary[f"{column}_reverted"] = 1

    quality_summary["blocked_rows"] = 0  # C10 reverts columns, never drops rows

    analysis_dataset_id = f"analysis_dataset_{dataset_id}_{profile.dataset_version}"
    result = AnalysisDataset(
        analysis_dataset_id=analysis_dataset_id,
        source_dataset_id=dataset_id, source_dataset_version=profile.dataset_version,
        row_count=row_count, transformations=transformations,
        quality_summary=quality_summary,
        lineage_map_ref=f"lineage/{analysis_dataset_id}",
        status="ready_with_warnings" if any_reverted else "ready",
    )

    store = AnalysisDatasetStore(dsn, workspace_id)
    try:
        store.save(result)
    finally:
        store.close()
    logger.info("preprocess ws=%s dataset=%s columns=%d reverted=%s",
               workspace_id, dataset_id, len(transformations), any_reverted)
    return result
