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

from aryx.andie_planner.models import DashboardSpec, Kpi
from aryx.spec_validation.models import CheckResult, ValidationError, ValidationWarning

_NUMERIC_OPS = {"sum", "average", "median"}
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
    "dangling_reference": "dangling_reference",
    "unknown_dataset": "unknown_dataset",
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


def check_json_schema(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """1. Required fields present: at least one business question and one KPI."""
    if spec.spec_status == "invalid" or not spec.business_questions or not spec.kpis:
        return (CheckResult(check="json_schema", status="failed"),
                [ValidationError(code="schema_invalid", path="$", reference="spec")], [])
    return CheckResult(check="json_schema", status="passed"), [], []


def check_column_existence(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """2. Every referenced field exists in the dataset profile."""
    errors = _promote(spec, "unapproved_column")
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
    """4. Numeric operations (sum/average/median) use a numeric measure."""
    errors: list[ValidationError] = []
    for kpi in spec.kpis:
        if kpi.operation in _NUMERIC_OPS and kpi.measure:
            col_type = _kpi_measure_type(kpi, ctx)
            if col_type is not None and col_type != "numeric":
                errors.append(ValidationError(code="type_mismatch", path=f"kpi:{kpi.kpi_id}.measure",
                                              reference=kpi.measure))
    status = "failed" if errors else "passed"
    return CheckResult(check="type_compatibility", status=status), errors, []


def check_operation_whitelist(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """5. Every operation is explicitly supported (catalogue-whitelisted)."""
    errors = _promote(spec, "unsupported_operation")
    status = "failed" if errors else "passed"
    return CheckResult(check="operation_whitelist", status=status), errors, []


def check_formula_validity(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """6. Ratio/percentage KPIs declare both a numerator and a denominator."""
    errors: list[ValidationError] = []
    for kpi in spec.kpis:
        if kpi.operation in _RATIO_OPS and (kpi.numerator is None or kpi.denominator is None):
            errors.append(ValidationError(code="formula_incoherent", path=f"kpi:{kpi.kpi_id}",
                                          reference=kpi.kpi_id))
    status = "failed" if errors else "passed"
    return CheckResult(check="formula_validation", status=status), errors, []


def check_division_by_zero_policy(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """7. Every ratio/percentage KPI declares a zero-denominator policy."""
    errors: list[ValidationError] = []
    for kpi in spec.kpis:
        if kpi.operation in _RATIO_OPS and not kpi.zero_denominator_policy:
            errors.append(ValidationError(code="missing_zero_denominator_policy",
                                          path=f"kpi:{kpi.kpi_id}.zero_denominator_policy",
                                          reference=kpi.kpi_id))
    status = "failed" if errors else "passed"
    return CheckResult(check="division_by_zero_policy", status=status), errors, []


def _viz_dataset_id(spec: DashboardSpec, source_ref: str) -> str:
    for kpi in spec.kpis:
        if kpi.kpi_id == source_ref:
            return kpi.dataset_id
    for a in spec.analyses:
        if a.analysis_id == source_ref:
            return a.dataset_id
    return ""


def check_chart_axis_compatibility(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """8. Chart type and axes are compatible (plus promoted chart/ref warnings)."""
    errors = _promote(spec, "unsupported_chart_type") + _promote(spec, "dangling_reference")
    for viz in spec.visualizations:
        if viz.chart_type != "scatter" or not viz.x_axis or not viz.y_axis:
            continue
        ds_id = _viz_dataset_id(spec, viz.source_ref)
        x_type = ctx.col_type(ds_id, viz.x_axis)
        y_type = ctx.col_type(ds_id, viz.y_axis)
        if x_type == "categorical" and y_type == "categorical":
            errors.append(ValidationError(code="incompatible_chart_axes",
                                          path=f"visualization:{viz.chart_id}",
                                          reference=viz.chart_id))
    status = "failed" if errors else "passed"
    return CheckResult(check="chart_axis_compatibility", status=status), errors, []


def check_lineage_declaration(spec: DashboardSpec, ctx: ValidationContext) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """9. Every KPI/analysis declares its source fields and operations."""
    errors: list[ValidationError] = []
    for kpi in spec.kpis:
        has_lineage = bool(kpi.source_columns or kpi.measure or kpi.numerator or kpi.denominator)
        if not has_lineage:
            errors.append(ValidationError(code="missing_lineage", path=f"kpi:{kpi.kpi_id}",
                                          reference=kpi.kpi_id))
    for a in spec.analyses:
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
