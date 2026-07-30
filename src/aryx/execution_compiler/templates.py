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
    "grouped_safe_ratio": frozenset({"group_column", "status_column"}),
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

# `operation` values C09 (spec_validation.checks._RATIO_OPS) already
# guarantees have both a numerator and a denominator by the time C11 runs.
RATIO_OPERATIONS = frozenset({"ratio", "percentage"})
