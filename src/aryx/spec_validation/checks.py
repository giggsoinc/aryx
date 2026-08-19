"""The 10 named C09 checks — pure, deterministic, no LLM, no I/O.

Each check takes the already-GROUNDED DashboardSpec (post C08 `ground_spec`)
plus a `ValidationContext` of approved resources, and returns
(CheckResult, errors, warnings). Several checks promote a C08 grounding
warning (recorded when ground.py silently stripped an invented reference) into
a hard C09 error — this is how a column the LLM invented but C08 already
dropped (e.g. `annual_revenue`) still surfaces as a rejection here: C08 warns
and continues, C09 treats the same evidence as disqualifying.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from aryx.andie_planner.models import Analysis, DashboardSpec, Kpi
from aryx.spec_validation.models import CheckResult, ValidationError, ValidationWarning

_NUMERIC_OPS = {"sum", "average", "median", "quartiles", "histogram"}
_RATIO_OPS = {"ratio", "percentage"}
_CLAIM_BLOCKLIST = (
    "forecast", "predict", "prediction", "will cause", "causes", "causing",
    "due to", "because of", "will increase", "will decrease", "projected to",
    "is caused by", "leads to",
)
_PATH_TOKEN_RE = re.compile(r"\bpath_[a-z0-9_]+\b", re.IGNORECASE)

# Maps a C08 grounding warning code to the C09 error code it's promoted to.
_PROMOTED_CODES = {
    "unapproved_column": "column_not_found",
    "unsupported_operation": "unsupported_operation",
    "unsupported_chart_type": "unsupported_chart_type",
    "unknown_dataset": "unknown_dataset",
    "missing_filter_value": "missing_filter_value",
}


@dataclass(frozen=True)
class ValidationContext:
    """Approved resources a candidate spec is checked against.

    Single-dataset mode: `approved_columns` is that dataset's flat name->type
    map, `columns_by_dataset` is empty. Workspace mode: `columns_by_dataset`
    is authoritative (dataset_id -> name->type), `approved_columns` is empty —
    mirrors ground.py's own dual-mode split.
    """

    approved_columns: dict[str, str] = field(default_factory=dict)
    columns_by_dataset: dict[str, dict[str, str]] = field(default_factory=dict)
    approved_graph_paths: frozenset[str] = frozenset()
    approved_operations: frozenset[str] = frozenset()
    approved_charts: frozenset[str] = frozenset()

    def col_type(self, dataset_id: str, name: str | None) -> str | None:
        if not name:
            return None
        if self.columns_by_dataset:
            return self.columns_by_dataset.get(dataset_id, {}).get(name)
        return self.approved_columns.get(name)


def _promote(spec: DashboardSpec, code: str) -> list[ValidationError]:
    """Turn every C08 grounding warning of `code` into a C09 error."""
    mapped = _PROMOTED_CODES[code]
    return [
        ValidationError(code=mapped, path=w.detail, reference=w.column or w.detail)
        for w in spec.warnings if w.code == code
    ]


def _dangling_reference_warnings(spec: DashboardSpec) -> list[ValidationWarning]:
    """A dangling chart/analysis reference is already self-healed by C08:
    `ground_spec` drops the offending visualization before it ever reaches
    the spec, so the rest of the spec (every other chart, KPI, analysis) is
    still fully valid. Rejecting the whole spec over one already-removed
    chart wastes a full LLM regeneration for something that never rendered
    anyway — surface it as a warning instead, not a blocking error."""
    return [ValidationWarning(code="dangling_reference", scope=w.detail)
           for w in spec.warnings if w.code == "dangling_reference"]




def check_json_schema(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """1. Required fields present: at least one business question and one KPI."""
    if spec.spec_status == "invalid" or not spec.business_questions or not spec.kpis:
        return (CheckResult(check="json_schema", status="failed"),
                [ValidationError(code="schema_invalid", path="$", reference="spec")], [])
    return CheckResult(check="json_schema", status="passed"), [], []


def check_column_existence(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """2. Every referenced field — and its dataset — exists in the workspace profile."""
    errors = _promote(spec, "unapproved_column") + _promote(spec, "unknown_dataset")
    status = "failed" if errors else "passed"
    return CheckResult(check="column_existence", status=status), errors, []


def check_graph_path_grounding(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """3. Every referenced graph path exists. DashboardSpec has no dedicated
    graph-path field yet, so this scans assumption text for path-like tokens
    (e.g. 'path_contract_manager_region') and confirms each is approved."""
    errors: list[ValidationError] = []
    for a in spec.assumptions:
        for token in _PATH_TOKEN_RE.findall(a.meaning):
            if token not in ctx.approved_graph_paths:
                errors.append(ValidationError(code="graph_path_not_found",
                                              path=f"assumption:{a.code}", reference=token))
    status = "failed" if errors else "passed"
    return CheckResult(check="graph_path_existence", status=status), errors, []


def _kpi_measure_type(kpi: Kpi, ctx: ValidationContext) -> str | None:
    return ctx.col_type(kpi.dataset_id, kpi.measure)


def check_type_compatibility(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """4. Numeric operations (sum/average/median) use a numeric measure.

    A KPI with `measure` unset entirely used to pass this check silently
    (the old condition only fired when `measure` was present but wrong) —
    C11 then compiles it against a literal empty column name (see
    execution_compiler.compile._compile_kpi), and C12 returns a fabricated
    value=0.0/sample_size=0 instead of a real result or a loud failure.
    `source_columns` (lineage-only) is not a substitute for `measure`."""
    errors: list[ValidationError] = []
    for kpi in spec.kpis:
        if kpi.operation not in _NUMERIC_OPS:
            continue
        if not kpi.measure:
            errors.append(ValidationError(code="missing_measure", path=f"kpi:{kpi.kpi_id}.measure",
                                          reference=kpi.kpi_id))
            continue
        col_type = _kpi_measure_type(kpi, ctx)
        if col_type is not None and col_type != "numeric":
            errors.append(ValidationError(code="type_mismatch", path=f"kpi:{kpi.kpi_id}.measure",
                                          reference=kpi.measure))
    errors.extend(_histogram_metric_errors(spec))
    status = "failed" if errors else "passed"
    return CheckResult(check="type_compatibility", status=status), errors, []


def _histogram_metric_errors(spec: DashboardSpec) -> list[ValidationError]:
    """A histogram Analysis must reference a histogram KPI to bucket.

    The analysis-level sibling of the missing-measure case above. A histogram
    needs a numeric column to bucket, and an Analysis carries no measure of
    its own — it borrows the one on its `metric` KPI. Point it at, say, a
    `count` KPI (no measure at all) and C11 cannot emit a histogram template,
    so it falls through to a grouped count; C12 then unpacks that `{group:
    int}` as `{group: {"buckets": ...}}` and raises. Catching it here lets
    the planner's one-shot repair retry fix the pairing before compilation.
    """
    kpis_by_id = {k.kpi_id: k for k in spec.kpis}
    errors: list[ValidationError] = []
    for analysis in spec.analyses:
        if analysis.operation != "histogram":
            continue
        metric_kpi = kpis_by_id.get(analysis.metric or "")
        if metric_kpi is not None and metric_kpi.operation == "histogram" \
                and metric_kpi.measure:
            continue
        errors.append(ValidationError(
            code="histogram_metric_mismatch",
            path=f"analysis:{analysis.analysis_id}.metric",
            reference=analysis.metric or ""))
    return errors


def check_operation_whitelist(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """5. Every operation is explicitly supported (catalogue-whitelisted)."""
    errors = _promote(spec, "unsupported_operation")
    status = "failed" if errors else "passed"
    return CheckResult(check="operation_whitelist", status=status), errors, []


def check_formula_validity(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """6. Ratio/percentage KPIs declare both a numerator and a denominator
    (plus promoted missing-filter-value errors: a filter with a column but no
    value/values would compile to filter_equals(column, None), matching
    nothing real — C08 already drops it, C09 treats the same evidence as
    disqualifying rather than letting the KPI/operand silently go unfiltered).

    Kept as a hard error, NOT loosened to a warning, despite being the most
    common rejection reason live this session: grounding drops only the
    invalid FILTER, not the whole operand — an operand with `filter=None`
    still computes an unfiltered count. For a ratio KPI that means a
    numerator/denominator meant to be "count where X" silently becomes
    "count of everything", producing a wrong, non-null percentage that would
    ship to the dashboard looking legitimate. That is a worse failure mode
    than the spec failing to generate, so this stays spec-fatal."""
    errors = _promote(spec, "missing_filter_value")
    for kpi in spec.kpis:
        if kpi.operation in _RATIO_OPS and (kpi.numerator is None or kpi.denominator is None):
            errors.append(ValidationError(code="formula_incoherent", path=f"kpi:{kpi.kpi_id}",
                                          reference=kpi.kpi_id))
    status = "failed" if errors else "passed"
    return CheckResult(check="formula_validation", status=status), errors, []


_IMPLEMENTED_ZERO_DENOMINATOR_POLICIES = {"return_null_with_warning"}


def check_division_by_zero_policy(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """7. Every ratio/percentage KPI declares a zero-denominator policy that
    C12/C13 actually implement — execute.py only ever returns null + warns,
    so any other declared policy would silently diverge from what runs."""
    errors: list[ValidationError] = []
    for kpi in spec.kpis:
        if kpi.operation not in _RATIO_OPS:
            continue
        if not kpi.zero_denominator_policy:
            errors.append(ValidationError(code="missing_zero_denominator_policy",
                                          path=f"kpi:{kpi.kpi_id}.zero_denominator_policy",
                                          reference=kpi.kpi_id))
        elif kpi.zero_denominator_policy not in _IMPLEMENTED_ZERO_DENOMINATOR_POLICIES:
            errors.append(ValidationError(
                code="unsupported_zero_denominator_policy",
                path=f"kpi:{kpi.kpi_id}.zero_denominator_policy={kpi.zero_denominator_policy!r}",
                reference=kpi.kpi_id))
    status = "failed" if errors else "passed"
    return CheckResult(check="division_by_zero_policy", status=status), errors, []


def _analysis_group_column(spec: DashboardSpec, analysis_id: str) -> str | None:
    for a in spec.analyses:
        if a.analysis_id == analysis_id:
            return a.group_by[0] if a.group_by else ""
    return None


def _find_analysis(spec: DashboardSpec, analysis_id: str) -> Analysis | None:
    return next((a for a in spec.analyses if a.analysis_id == analysis_id), None)


# chart_type -> the Analysis.operation its source_ref's Analysis must have.
_CROSSTAB_CHART_TYPES = frozenset(
    {"sankey", "treemap", "sunburst", "heatmap_matrix", "calendar_heatmap"})


def _chart_shape_error(viz_chart_id: str) -> ValidationError:
    return ValidationError(code="incompatible_chart_axes", path=f"visualization:{viz_chart_id}",
                           reference=viz_chart_id)


def check_chart_axis_compatibility(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """8. Chart type and axes/shape are compatible (plus promoted chart-type
    errors and non-blocking dangling-reference warnings). Beyond the
    original grouped_bar/scatter rules, every new chart family that needs a
    specific Analysis shape (crosstab/row_points/date_span/survival/
    histogram) or a specific Visualization field (radar's axis_refs) gets
    its own structural rule here — same "promote a shape mismatch to a hard
    error" pattern as the original two."""
    errors = _promote(spec, "unsupported_chart_type")
    for viz in spec.visualizations:
        if viz.chart_type == "grouped_bar" and viz.compare_ref:
            # A grouped bar merges two analyses' rows by group_value on the
            # frontend — merging across mismatched group_by dimensions would
            # silently produce a meaningless chart, so both sides must share
            # the exact same group-by column.
            source_col = _analysis_group_column(spec, viz.source_ref)
            compare_col = _analysis_group_column(spec, viz.compare_ref)
            if source_col is None or compare_col is None or source_col != compare_col:
                errors.append(_chart_shape_error(viz.chart_id))
            continue

        if viz.chart_type in _CROSSTAB_CHART_TYPES:
            a = _find_analysis(spec, viz.source_ref)
            if a is None or a.operation != "crosstab" or len(a.group_by) != 2:
                errors.append(_chart_shape_error(viz.chart_id))
            continue

        if viz.chart_type == "gantt":
            a = _find_analysis(spec, viz.source_ref)
            if a is None or a.operation != "date_span" or not a.start_column or not a.end_column:
                errors.append(_chart_shape_error(viz.chart_id))
            continue

        if viz.chart_type == "survival_curve":
            a = _find_analysis(spec, viz.source_ref)
            if a is None or a.operation != "survival" or not a.start_column:
                errors.append(_chart_shape_error(viz.chart_id))
            continue

        if viz.chart_type in ("scatter", "bubble"):
            a = _find_analysis(spec, viz.source_ref)
            if a is None or a.operation != "row_points" or not a.x_column or not a.y_column:
                errors.append(_chart_shape_error(viz.chart_id))
                continue
            if viz.chart_type == "bubble" and not a.size_column:
                errors.append(_chart_shape_error(viz.chart_id))
            continue

        if viz.chart_type == "histogram":
            a = _find_analysis(spec, viz.source_ref)
            if a is None or a.operation != "histogram":
                errors.append(_chart_shape_error(viz.chart_id))
            continue

        if viz.chart_type == "radar":
            refs = viz.axis_refs or []
            valid_refs = {k.kpi_id for k in spec.kpis} | {a.analysis_id for a in spec.analyses}
            if len(refs) < 3 or any(r not in valid_refs for r in refs):
                errors.append(_chart_shape_error(viz.chart_id))
            continue

        a = _find_analysis(spec, viz.source_ref)
        if a is not None and a.operation == "graph_relation" \
                and viz.chart_type not in ("bar", "donut", "kpi_card"):
            # graph_relation produces one count per related entity — a 1D
            # grouped shape, not the 2D crosstab shape sankey/treemap/
            # heatmap_matrix need.
            errors.append(_chart_shape_error(viz.chart_id))
            continue

    status = "failed" if errors else "passed"
    return (CheckResult(check="chart_axis_compatibility", status=status), errors,
           _dangling_reference_warnings(spec))


def check_lineage_declaration(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """9. Every KPI/analysis declares its source fields and operations."""
    errors: list[ValidationError] = []
    for kpi in spec.kpis:
        has_lineage = bool(kpi.source_columns or kpi.measure or kpi.numerator or kpi.denominator)
        if not has_lineage:
            errors.append(ValidationError(code="missing_lineage", path=f"kpi:{kpi.kpi_id}",
                                          reference=kpi.kpi_id))
    for a in spec.analyses:
        if a.operation == "graph_relation":
            # A graph_relation analysis's lineage IS its graph_path_id (a
            # verified C06 path), not group_by/metric — it has neither.
            if not a.graph_path_id:
                errors.append(ValidationError(code="missing_lineage",
                                              path=f"analysis:{a.analysis_id}",
                                              reference=a.analysis_id))
            continue
        if not (a.group_by or a.metric):
            errors.append(ValidationError(code="missing_lineage", path=f"analysis:{a.analysis_id}",
                                          reference=a.analysis_id))
    status = "failed" if errors else "passed"
    return CheckResult(check="lineage_declaration", status=status), errors, []


def check_claim_safety(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """10. Reject unsupported causal or predictive claims (fixed blocklist)."""
    errors: list[ValidationError] = []
    for q in spec.business_questions:
        low = q.text.lower()
        for term in _CLAIM_BLOCKLIST:
            if term in low:
                errors.append(ValidationError(code="unsupported_claim",
                                              path=f"business_question:{q.question_id}",
                                              reference=term))
    for a in spec.assumptions:
        low = a.meaning.lower()
        for term in _CLAIM_BLOCKLIST:
            if term in low:
                errors.append(ValidationError(code="unsupported_claim",
                                              path=f"assumption:{a.code}", reference=term))
    status = "failed" if errors else "passed"
    return CheckResult(check="unsupported_claims", status=status), errors, []


ALL_CHECKS = (
    check_json_schema,
    check_column_existence,
    check_graph_path_grounding,
    check_type_compatibility,
    check_operation_whitelist,
    check_formula_validity,
    check_division_by_zero_policy,
    check_chart_axis_compatibility,
    check_lineage_declaration,
    check_claim_safety,
)
