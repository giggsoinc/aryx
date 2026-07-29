"""Tests for Pre-Execution Specification Validation (C09) — no DB, no LLM.

checks.py/validate.py are pure and deterministic, tested directly against
DashboardSpec objects built via C08's real `ground_spec` (so the promoted
grounding-warning path is exercised against real ground.py behavior, not a
mock). The DB-backed attempt-cap/persistence layer (spec_validation/run.py,
SpecValidationStore) needs a real Postgres connection and is not covered here.
"""
from __future__ import annotations

from aryx.andie_planner.ground import ground_spec
from aryx.spec_validation.checks import ALL_CHECKS, ValidationContext
from aryx.spec_validation.validate import repair_constraints_text, validate_spec

APPROVED_COLUMNS = [
    {"name": "contract_id", "type": "identifier"},
    {"name": "region", "type": "categorical"},
    {"name": "contract_value", "type": "numeric"},
    {"name": "renewal_status", "type": "categorical"},
    {"name": "renewal_date", "type": "datetime"},
]
APPROVED_OPS = ["count", "sum", "ratio", "group_by"]
APPROVED_CHARTS = ["kpi_card", "bar", "scatter", "table"]
APPROVED_PATHS = ["path_contract_manager_region"]

GOOD_RAW = {
    "business_questions": [
        {"question_id": "bq_001", "text": "What is the renewal rate?"},
        {"question_id": "bq_002", "text": "Which regions renew least?"},
        {"question_id": "bq_003", "text": "What is the renewed contract value?"},
    ],
    "kpis": [
        {
            "kpi_id": "kpi_renewal_rate", "name": "Renewal Rate",
            "source_columns": ["renewal_status", "contract_id"], "operation": "ratio",
            "numerator": {"operation": "count",
                          "filter": {"column": "renewal_status", "operator": "equals",
                                    "value": "Renewed"}},
            "denominator": {"operation": "count",
                            "filter": {"column": "renewal_status", "operator": "in",
                                      "values": ["Renewed", "Not Renewed"]}},
            "zero_denominator_policy": "return_null_with_warning", "format": "percentage",
        },
        {
            "kpi_id": "kpi_renewed_value", "name": "Renewed Contract Value",
            "source_columns": ["contract_value"], "operation": "sum",
            "measure": "contract_value", "format": "currency",
        },
    ],
    "analyses": [
        {"analysis_id": "analysis_renewal_by_region", "operation": "group_by",
         "group_by": ["region"], "metric": "kpi_renewal_rate"},
    ],
    "visualizations": [
        {"chart_id": "chart_renewal_rate", "chart_type": "kpi_card", "source_ref": "kpi_renewal_rate"},
        {"chart_id": "chart_renewal_by_region", "chart_type": "bar",
         "source_ref": "analysis_renewal_by_region", "x_axis": "region", "y_axis": "renewal_rate"},
    ],
    "assumptions": [{"code": "path_used", "meaning": "Uses path_contract_manager_region for context."}],
    "warnings": [],
}


def _ground(raw):
    return ground_spec(
        raw, dataset_id="dataset_contracts", dataset_version="v1",
        approved_columns=APPROVED_COLUMNS, approved_operations=APPROVED_OPS,
        approved_charts=APPROVED_CHARTS,
    )


def _ctx(**overrides):
    kwargs = dict(
        approved_columns={c["name"]: c["type"] for c in APPROVED_COLUMNS},
        approved_graph_paths=frozenset(APPROVED_PATHS),
        approved_operations=frozenset(APPROVED_OPS),
        approved_charts=frozenset(APPROVED_CHARTS),
    )
    kwargs.update(overrides)
    return ValidationContext(**kwargs)


# ── happy path ───────────────────────────────────────────────────────────

def test_clean_spec_approved_by_all_ten_checks() -> None:
    spec = _ground(GOOD_RAW)
    report, repair = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert report.status == "approved"
    assert report.eligible_for_compilation is True
    assert repair is None
    assert len(report.checks) == len(ALL_CHECKS) == 10
    assert all(c.status == "passed" for c in report.checks)
    assert report.errors == []


# ── 1. json schema ───────────────────────────────────────────────────────

def test_empty_spec_fails_json_schema() -> None:
    spec = _ground({})
    report, repair = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert report.status == "rejected"
    assert any(e.code == "schema_invalid" for e in report.errors)
    assert repair is not None
    assert report.retry.allowed is True
    assert report.retry.remaining_attempts == 1


# ── 2. column existence (promoted from ground.py's unapproved_column) ────

def test_invented_column_fails_column_existence() -> None:
    raw = dict(GOOD_RAW, kpis=[{
        "kpi_id": "kpi_bad", "operation": "sum",
        "source_columns": ["annual_revenue"], "measure": "annual_revenue",
    }])
    spec = _ground(raw)
    report, repair = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert report.status == "rejected"
    col_errors = [e for e in report.errors if e.code == "column_not_found"]
    assert col_errors and any(e.reference == "annual_revenue" for e in col_errors)
    assert repair.errors[0].allowed_columns == sorted(c["name"] for c in APPROVED_COLUMNS)


# ── 3. graph path grounding ──────────────────────────────────────────────

def test_unapproved_graph_path_token_in_assumption_fails() -> None:
    raw = dict(GOOD_RAW, assumptions=[
        {"code": "path_used", "meaning": "Uses path_ghost_nonexistent for context."},
    ])
    spec = _ground(raw)
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert any(e.code == "graph_path_not_found" for e in report.errors)


def test_approved_graph_path_token_passes() -> None:
    spec = _ground(GOOD_RAW)  # assumption references path_contract_manager_region
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert not any(e.code == "graph_path_not_found" for e in report.errors)


# ── 4. type compatibility ────────────────────────────────────────────────

def test_numeric_operation_on_categorical_measure_fails_type_check() -> None:
    raw = dict(GOOD_RAW, kpis=[{
        "kpi_id": "kpi_bad", "operation": "sum",
        "source_columns": ["region"], "measure": "region",
    }])
    spec = _ground(raw)
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert any(e.code == "type_mismatch" and e.reference == "region" for e in report.errors)


# ── 5. operation whitelist (promoted from ground.py) ─────────────────────

def test_unsupported_operation_fails_whitelist_check() -> None:
    raw = dict(GOOD_RAW, kpis=[{
        "kpi_id": "kpi_bad", "operation": "forecast", "source_columns": ["contract_value"],
    }])
    spec = _ground(raw)
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert any(e.code == "unsupported_operation" for e in report.errors)


# ── 6. formula validity ──────────────────────────────────────────────────

def test_ratio_without_denominator_fails_formula_validity() -> None:
    raw = dict(GOOD_RAW, kpis=[{
        "kpi_id": "kpi_bad", "operation": "ratio", "source_columns": ["contract_value"],
        "numerator": {"operation": "count"},
        "zero_denominator_policy": "return_null_with_warning",
    }])
    spec = _ground(raw)
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert any(e.code == "formula_incoherent" for e in report.errors)


# ── 7. division-by-zero policy ───────────────────────────────────────────

def test_ratio_without_zero_denominator_policy_fails() -> None:
    raw = dict(GOOD_RAW, kpis=[{
        "kpi_id": "kpi_bad", "operation": "ratio", "source_columns": ["contract_value"],
        "numerator": {"operation": "count"}, "denominator": {"operation": "count"},
    }])
    spec = _ground(raw)
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert any(e.code == "missing_zero_denominator_policy" for e in report.errors)


# ── 8. chart/axis compatibility ──────────────────────────────────────────

def test_scatter_with_two_categorical_axes_fails() -> None:
    raw = dict(GOOD_RAW, visualizations=[
        {"chart_id": "c1", "chart_type": "scatter", "source_ref": "kpi_renewal_rate",
         "x_axis": "region", "y_axis": "renewal_status"},
    ])
    spec = _ground(raw)
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert any(e.code == "incompatible_chart_axes" and e.reference == "c1" for e in report.errors)


def test_scatter_with_numeric_axis_passes_axis_check() -> None:
    raw = dict(GOOD_RAW, visualizations=[
        {"chart_id": "c1", "chart_type": "scatter", "source_ref": "kpi_renewal_rate",
         "x_axis": "region", "y_axis": "contract_value"},
    ])
    spec = _ground(raw)
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert not any(e.code == "incompatible_chart_axes" for e in report.errors)


# ── 9. lineage declaration ───────────────────────────────────────────────

def test_kpi_with_no_lineage_fails() -> None:
    raw = dict(GOOD_RAW, kpis=[{"kpi_id": "kpi_bad", "operation": "count"}])
    spec = _ground(raw)
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert any(e.code == "missing_lineage" and e.reference == "kpi_bad" for e in report.errors)


# ── 10. claim safety ─────────────────────────────────────────────────────

def test_predictive_claim_in_business_question_fails() -> None:
    raw = dict(GOOD_RAW, business_questions=[
        {"question_id": "bq_001", "text": "What will the renewal rate be next quarter (forecast)?"},
        {"question_id": "bq_002", "text": "Which regions renew least?"},
        {"question_id": "bq_003", "text": "What is the renewed contract value?"},
    ])
    spec = _ground(raw)
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert any(e.code == "unsupported_claim" for e in report.errors)


def test_causal_claim_in_assumption_fails() -> None:
    raw = dict(GOOD_RAW, assumptions=[
        {"code": "a1", "meaning": "Region West underperforms because of poor management."},
    ])
    spec = _ground(raw)
    report, _ = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert any(e.code == "unsupported_claim" for e in report.errors)


# ── attempt/retry bookkeeping ─────────────────────────────────────────────

def test_second_attempt_has_no_remaining_retries() -> None:
    spec = _ground({})
    report, repair = validate_spec(spec, _ctx(), validation_id="v1", attempt=2)
    assert report.status == "rejected"
    assert report.retry.allowed is False
    assert report.retry.remaining_attempts == 0
    assert repair is None  # cap reached — no further repair request issued


def test_repair_constraints_text_renders_readable_instructions() -> None:
    raw = dict(GOOD_RAW, kpis=[{
        "kpi_id": "kpi_bad", "operation": "forecast", "source_columns": ["annual_revenue"],
    }])
    spec = _ground(raw)
    report, repair = validate_spec(spec, _ctx(), validation_id="v1", attempt=1)
    assert repair is not None
    text = repair_constraints_text(repair)
    assert "REJECTED" in text
    assert "unsupported_operation" in text


# ── workspace (multi-dataset) mode ───────────────────────────────────────

WORKSPACE_DATASETS = [
    {"dataset_id": "dataset_item", "approved_columns": [
        {"name": "model", "type": "categorical"},
        {"name": "fields.cost", "type": "numeric"},
    ]},
]


def test_workspace_mode_type_check_uses_the_kpis_own_dataset() -> None:
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [{"kpi_id": "kpi_bad", "operation": "sum", "dataset_id": "dataset_item",
                 "source_columns": ["model"], "measure": "model"}],
    }
    spec = ground_spec(
        raw, dataset_id="workspace_1", dataset_version="v1",
        approved_columns=[], approved_operations=APPROVED_OPS,
        approved_charts=APPROVED_CHARTS, datasets=WORKSPACE_DATASETS,
    )
    ctx = _ctx(approved_columns={},
              columns_by_dataset={"dataset_item": {"model": "categorical", "fields.cost": "numeric"}})
    report, _ = validate_spec(spec, ctx, validation_id="v1", attempt=1)
    assert any(e.code == "type_mismatch" and e.reference == "model" for e in report.errors)
