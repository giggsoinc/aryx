"""Pin schema.py's enum constraints (C08) to their real sources of truth.

These enums are additive structural guardrails against model hallucination
(see andie_planner/schema.py's module docstring) — this file exists so a
future change to planning.catalogues or the ratio-operand/zero-denominator
rules can't silently desync the JSON schema without a test catching it.
"""
from __future__ import annotations

from aryx.andie_planner.schema import (
    DASHBOARD_SPEC_SCHEMA,
    DELTA_SPEC_SCHEMA,
    _RATIO_OPERAND_SCHEMA,
    _ZERO_DENOMINATOR_POLICY_SCHEMA,
)
from aryx.execution_compiler.templates import NUMERIC_TEMPLATES
from aryx.planning.catalogues import CHARTS, OPERATIONS
from aryx.spec_validation.checks import _IMPLEMENTED_ZERO_DENOMINATOR_POLICIES


def test_kpi_and_analysis_operation_enum_matches_the_real_catalogue() -> None:
    kpi_schema = DASHBOARD_SPEC_SCHEMA["properties"]["kpis"]["items"]["properties"]["operation"]
    analysis_schema = DASHBOARD_SPEC_SCHEMA["properties"]["analyses"]["items"]["properties"]["operation"]
    assert kpi_schema["enum"] == OPERATIONS
    assert analysis_schema["enum"] == OPERATIONS


def test_delta_operation_enum_matches_the_real_catalogue() -> None:
    new_kpi = DELTA_SPEC_SCHEMA["properties"]["new_kpi"]["properties"]["operation"]
    new_analysis = DELTA_SPEC_SCHEMA["properties"]["new_analysis"]["properties"]["operation"]
    assert new_kpi["enum"] == OPERATIONS
    assert new_analysis["enum"] == OPERATIONS


def test_chart_type_enum_matches_the_real_catalogue() -> None:
    viz_schema = DASHBOARD_SPEC_SCHEMA["properties"]["visualizations"]["items"]["properties"]["chart_type"]
    delta_viz_schema = DELTA_SPEC_SCHEMA["properties"]["new_visualization"]["properties"]["chart_type"]
    assert viz_schema["enum"] == CHARTS
    assert delta_viz_schema["enum"] == CHARTS


def test_zero_denominator_policy_enum_matches_the_implemented_set() -> None:
    # Only C12/C13 actually implement "return_null_with_warning" (see
    # spec_validation.checks.check_division_by_zero_policy) — the schema's
    # enum must never drift ahead of what the executor can actually do.
    assert set(_ZERO_DENOMINATOR_POLICY_SCHEMA["enum"]) == _IMPLEMENTED_ZERO_DENOMINATOR_POLICIES


def test_ratio_operand_operation_enum_excludes_uncompilable_operations() -> None:
    # C11's _compile_operand has no column to bind sum/average/median to for
    # a ratio numerator/denominator (see execution_compiler.validate's
    # check_ratio_operand_operations) — "count" must be the only allowed
    # value, and none of NUMERIC_TEMPLATES' keys may ever be allowed here.
    allowed = set(_RATIO_OPERAND_SCHEMA["properties"]["operation"]["enum"])
    assert allowed == {"count"}
    assert allowed.isdisjoint(NUMERIC_TEMPLATES)


def test_numerator_and_denominator_share_the_same_operand_schema() -> None:
    kpi_props = DASHBOARD_SPEC_SCHEMA["properties"]["kpis"]["items"]["properties"]
    assert kpi_props["numerator"] is _RATIO_OPERAND_SCHEMA
    assert kpi_props["denominator"] is _RATIO_OPERAND_SCHEMA
    delta_kpi_props = DELTA_SPEC_SCHEMA["properties"]["new_kpi"]["properties"]
    assert delta_kpi_props["numerator"] is _RATIO_OPERAND_SCHEMA
    assert delta_kpi_props["denominator"] is _RATIO_OPERAND_SCHEMA
