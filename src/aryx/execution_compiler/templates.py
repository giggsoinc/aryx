"""Vetted operation templates (C11) — the ONLY operations the compiler may
bind parameters to. An operation with no template here has no execution
path: the compiler rejects the node rather than improvising SQL/Python for
it (see compile.py's module docstring).

Each entry maps a template name to the exact set of parameter keys a node
using it must carry — no more, no fewer (checked by validate.validate_bindings).
"""
from __future__ import annotations

TEMPLATES: dict[str, frozenset[str]] = {
    "filter_equals": frozenset({"column", "value"}),
    "filter_in": frozenset({"column", "values"}),
    "count_rows": frozenset(),
    "sum_numeric": frozenset({"column", "null_policy"}),
    "average_numeric": frozenset({"column", "null_policy"}),
    "median_numeric": frozenset({"column", "null_policy"}),
    "safe_ratio": frozenset({"numerator_ref", "denominator_ref", "zero_policy"}),
    "grouped_count_rows": frozenset({"group_column"}),
    "grouped_sum_numeric": frozenset({"group_column", "column", "null_policy"}),
    "grouped_average_numeric": frozenset({"group_column", "column", "null_policy"}),
    "grouped_median_numeric": frozenset({"group_column", "column", "null_policy"}),
    "grouped_safe_ratio": frozenset({"group_column", "status_column",
                                     "numerator_values", "denominator_values", "zero_policy"}),
    "quartiles_numeric": frozenset({"column", "null_policy"}),
    "grouped_quartiles_numeric": frozenset({"group_column", "column", "null_policy"}),
    "grouped2d_count_rows": frozenset({"group_column", "group_column_2"}),
    "grouped2d_sum_numeric": frozenset({"group_column", "group_column_2", "column", "null_policy"}),
    "grouped2d_average_numeric": frozenset({"group_column", "group_column_2", "column", "null_policy"}),
    "grouped2d_median_numeric": frozenset({"group_column", "group_column_2", "column", "null_policy"}),
    "grouped2d_safe_ratio": frozenset({"group_column", "group_column_2", "status_column",
                                       "numerator_values", "denominator_values", "zero_policy"}),
    "row_points": frozenset({"label_column", "x_column", "y_column", "size_column"}),
    "row_date_spans": frozenset({"label_column", "start_column", "end_column"}),
    "survival_curve": frozenset({"group_column", "start_column", "end_column"}),
    "histogram_buckets_numeric": frozenset({"column", "null_policy"}),
    "grouped_histogram_buckets_numeric": frozenset({"group_column", "column", "null_policy"}),
    "graph_relation_count": frozenset({"path_id"}),
}

# KPI/analysis `operation` (C08/C09 vocabulary — see spec_validation.checks
# ._NUMERIC_OPS) -> the per-row numeric template it compiles to.
NUMERIC_TEMPLATES: dict[str, str] = {
    "sum": "sum_numeric",
    "average": "average_numeric",
    "median": "median_numeric",
}

# Same numeric operations, grouped-by variant — used when an Analysis's
# `metric` points at a sum/average/median KPI.
GROUPED_NUMERIC_TEMPLATES: dict[str, str] = {
    "sum": "grouped_sum_numeric",
    "average": "grouped_average_numeric",
    "median": "grouped_median_numeric",
}

# "quartiles" is kept separate from NUMERIC_TEMPLATES/GROUPED_NUMERIC_TEMPLATES
# (rather than folded in) because its result shape is a 5-statistic dict
# (min/q1/median/q3/max), not a single scalar "value" — see
# analysis_execution.execute._kpi_result_from_node's dedicated branch for it.
QUARTILE_TEMPLATES: dict[str, str] = {"quartiles": "quartiles_numeric"}
GROUPED_QUARTILE_TEMPLATES: dict[str, str] = {"quartiles": "grouped_quartiles_numeric"}

# `operation` values C09 (spec_validation.checks._RATIO_OPS) already
# guarantees have both a numerator and a denominator by the time C11 runs.
RATIO_OPERATIONS = frozenset({"ratio", "percentage"})

# Analysis.operation == "histogram" mirrors "quartiles": the KPI carries the
# measure column, the Analysis carries the (optional) grouping.
HISTOGRAM_TEMPLATES: dict[str, str] = {"histogram": "histogram_buckets_numeric"}
GROUPED_HISTOGRAM_TEMPLATES: dict[str, str] = {"histogram": "grouped_histogram_buckets_numeric"}

# Analysis.operation == "crosstab" (group_by has exactly 2 columns) dispatches
# on the referenced KPI's own operation, same convention as
# GROUPED_NUMERIC_TEMPLATES/GROUPED_QUARTILE_TEMPLATES.
GROUPED_2D_NUMERIC_TEMPLATES: dict[str, str] = {
    "sum": "grouped2d_sum_numeric", "average": "grouped2d_average_numeric",
    "median": "grouped2d_median_numeric",
}
