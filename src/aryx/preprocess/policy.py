"""Deterministic conversion/null policy derivation for C10.

No authoring surface: policies are fully derived from (a) C03's own
canonical_type per column and (b) exactly the columns the APPROVED spec
references for one dataset — never the whole dataset, never user-typed.
"""
from __future__ import annotations

from aryx.andie_planner.models import DashboardSpec
from aryx.profiler.models import DatasetProfile

_CONVERSION_BY_TYPE = {
    "numeric": "numeric_conversion",
    "datetime": "date_conversion",
    "boolean": "boolean_conversion",
    "categorical": "trim_and_normalize_category",
    "identifier": "trim_whitespace",
    "text": "trim_whitespace",
    "empty": "trim_whitespace",
}

_AGGREGATION_OPS = {"sum", "average", "median", "ratio", "percentage"}


def referenced_columns(spec: DashboardSpec, dataset_id: str) -> set[str]:
    """Every column the approved spec actually touches for ONE dataset.

    ground.py always populates kpi.dataset_id/analysis.dataset_id (the target
    dataset in single-dataset mode, the declared dataset in workspace mode),
    so filtering by dataset_id is uniform across both modes.
    """
    cols: set[str] = set()
    for kpi in spec.kpis:
        if kpi.dataset_id and kpi.dataset_id != dataset_id:
            continue
        cols.update(kpi.source_columns)
        if kpi.measure:
            cols.add(kpi.measure)
        if kpi.filter:
            cols.add(kpi.filter.column)
        for operand in (kpi.numerator, kpi.denominator):
            if operand and operand.filter:
                cols.add(operand.filter.column)
    for analysis in spec.analyses:
        if analysis.dataset_id and analysis.dataset_id != dataset_id:
            continue
        cols.update(analysis.group_by)
    # Visualizations carry no dataset_id (implied by source_ref) — axes are
    # cosmetic display fields, harmless to include even if scoped elsewhere;
    # derive_conversion_policy silently skips names absent from THIS profile.
    for viz in spec.visualizations:
        if viz.x_axis:
            cols.add(viz.x_axis)
        if viz.y_axis:
            cols.add(viz.y_axis)
    return cols


def derive_conversion_policy(profile: DatasetProfile, columns: set[str]) -> dict[str, str]:
    """column -> conversion operation, purely from C03's canonical_type."""
    by_name = {c.name: c for c in profile.columns}
    return {
        name: _CONVERSION_BY_TYPE.get(by_name[name].canonical_type, "trim_whitespace")
        for name in columns if name in by_name
    }


def derive_null_policy(spec: DashboardSpec, columns: set[str], dataset_id: str) -> dict[str, str]:
    """column -> null-handling rule. Fixed default (no authoring surface):
    a column feeding a numeric aggregation excludes nulls from that
    aggregate; every other referenced column simply retains its nulls."""
    aggregated: set[str] = set()
    for kpi in spec.kpis:
        if kpi.dataset_id and kpi.dataset_id != dataset_id:
            continue
        if kpi.operation in _AGGREGATION_OPS and kpi.measure:
            aggregated.add(kpi.measure)
    return {name: ("exclude_from_aggregation" if name in aggregated else "retain")
            for name in columns}
