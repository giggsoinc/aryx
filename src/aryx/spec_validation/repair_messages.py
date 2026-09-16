"""Per-error-code repair instructions for C09's one-shot planner retry.

Split out of `validate.py` (raven-plan's 150-line file-size discipline) —
this module only knows how to phrase ONE error as one precise, imperative
sentence; `validate.py` owns running the checks and assembling the report.
"""
from __future__ import annotations

import difflib

from aryx.spec_validation.models import RepairErrorConstraint


def render_repair_line(err: RepairErrorConstraint) -> str:
    """One precise, imperative instruction per error — echoing the exact
    invented value inline (not just a bare allowed-list) so a small/weak
    model can find-and-replace it instead of re-guessing from scratch."""
    wrote = f" You wrote {err.invalid_value!r}." if err.invalid_value else ""
    if err.code == "formula_incoherent":
        return (f"- [{err.code}] at {err.path}. KPI {err.invalid_value!r} is a ratio/percentage "
               "KPI missing its numerator and/or denominator. Add BOTH fields, each shaped like "
               '{"operation": "count", "filter": {"column": "<real column>", "value": "<value>"}}.')
    if err.code in ("missing_zero_denominator_policy", "unsupported_zero_denominator_policy"):
        return (f"- [{err.code}] at {err.path}. KPI {err.invalid_value!r} must set "
               'zero_denominator_policy to EXACTLY "return_null_with_warning" — the only '
               "supported value (copy verbatim, do not invent another policy string).")
    if err.code == "missing_measure":
        return (f"- [{err.code}] at {err.path}. KPI {err.invalid_value!r} has a sum/average/median "
               "operation but no measure field. Add a measure field naming the ONE real numeric "
               "column to aggregate — source_columns alone is not enough, measure is required.")
    if err.code == "histogram_metric_mismatch":
        return (f"- [{err.code}] at {err.path}.{wrote} A histogram Analysis's "
               'metric must reference a KPI whose own operation is EXACTLY '
               '"histogram" (with a measure naming the real numeric column to '
               "bucket) — an aggregate KPI like sum/average/ratio has no "
               "per-row distribution to chart. Either change that KPI's "
               'operation to "histogram" and add a measure field, point '
               'metric at a different KPI that already has operation='
               '"histogram", or remove this histogram analysis entirely if no '
               "numeric column needs a distribution chart.")
    if err.code == "missing_filter_value":
        return (f"- [{err.code}] at {err.path}. The filter on column {err.invalid_value!r} has no "
               '"value" (or "values") — a filter with only a column name matches nothing. Add the '
               "actual value(s) to filter for, e.g. "
               '{"column": ' + repr(err.invalid_value) + ', "operator": "equals", "value": '
               '"<the real value to match>"}.')
    if err.allowed_columns is not None:
        hint = ""
        if err.invalid_value:
            close = difflib.get_close_matches(err.invalid_value, err.allowed_columns, n=1)
            if close:
                hint = f" The closest real column is {close[0]!r} — that is very likely the one you meant."
        return (f"- [{err.code}] at {err.path}.{wrote} Replace it with EXACTLY "
               f"one of these real column names (copy verbatim, case-sensitive): "
               f"{err.allowed_columns}.{hint}")
    if err.allowed_operations is not None:
        return (f"- [{err.code}] at {err.path}.{wrote} Use EXACTLY one of these "
               f"real operations (copy verbatim): {err.allowed_operations}.")
    if err.allowed_replacements is not None:
        return (f"- [{err.code}] at {err.path}.{wrote} Use EXACTLY one of these "
               f"chart types instead (copy verbatim): {err.allowed_replacements}.")
    return f"- [{err.code}] at {err.path}.{wrote} Remove this item — it has no valid replacement."
