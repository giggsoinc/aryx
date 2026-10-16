"""Tests for the targeted missing_filter_value micro-repair (C08 addendum).

Pure and deterministic — a fake complete_json_fn, no real LLM, no DB. Every
test proves the "never invent" guarantee holds even when the repair itself
fails or the model returns something unusable.
"""
from __future__ import annotations

from aryx.andie_planner.filter_repair import _parse_detail, repair_missing_filters
from aryx.andie_planner.models import (
    Analysis, DashboardSpec, Kpi, KpiFilter, KpiOperand, SpecWarning, Visualization,
)

APPROVED_COLUMNS = [
    {"name": "status", "type": "categorical",
     "sample_values": ["ACTIVE", "DRAFT", "EXPIRED", "TERMINATED"]},
    {"name": "renewal_status", "type": "categorical",
     "sample_values": ["Renewed", "Not Renewed"]},
    {"name": "is_renewed", "type": "boolean", "sample_values": ["0", "1"]},
]


class _FakeBroker:
    def choose(self, tier):
        from types import SimpleNamespace
        return SimpleNamespace(name="fake-model")


def _fake_complete_json(payload: dict):
    def fn(broker, tier, system, user, schema):
        return payload
    return fn


def _spec_with_broken_filter() -> DashboardSpec:
    kpi = Kpi(kpi_id="kpi_active_count", name="Active Contracts Count",
             dataset_id="ds1", operation="count", source_columns=["status"])
    warning = SpecWarning(code="missing_filter_value", column="status",
                          detail="kpi kpi_active_count.filter")
    return DashboardSpec(spec_id="s1", dataset_id="ds1", dataset_version="v1",
                         kpis=[kpi], warnings=[warning])


def _spec_with_broken_ratio_filter() -> DashboardSpec:
    kpi = Kpi(kpi_id="kpi_renewal_rate", name="Renewal Rate", dataset_id="ds1",
             operation="percentage", zero_denominator_policy="return_null_with_warning",
             numerator=KpiOperand(operation="count"),
             denominator=KpiOperand(operation="count",
                                    filter=KpiFilter(column="renewal_status",
                                                     values=["Renewed", "Not Renewed"])))
    warning = SpecWarning(code="missing_filter_value", column="renewal_status",
                          detail="kpi kpi_renewal_rate.numerator.filter")
    return DashboardSpec(spec_id="s1", dataset_id="ds1", dataset_version="v1",
                         kpis=[kpi], warnings=[warning])


# ── _parse_detail ────────────────────────────────────────────────────────

def test_parse_detail_plain_filter() -> None:
    assert _parse_detail("kpi kpi_x.filter") == ("kpi_x", "filter")


def test_parse_detail_numerator_filter() -> None:
    assert _parse_detail("kpi kpi_x.numerator.filter") == ("kpi_x", "numerator")


def test_parse_detail_denominator_filter() -> None:
    assert _parse_detail("kpi kpi_x.denominator.filter") == ("kpi_x", "denominator")


def test_parse_detail_rejects_unrelated_shapes() -> None:
    assert _parse_detail("analysis a1.group_by") is None
    assert _parse_detail("kpi kpi_x.measure") is None
    assert _parse_detail("") is None


# ── repair_missing_filters — plain filter ───────────────────────────────

def test_repairs_a_plain_filter_with_a_real_sample_value() -> None:
    spec = _spec_with_broken_filter()
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json(
            {"fills": [{"kpi_id": "kpi_active_count", "field": "filter", "value": "ACTIVE"}]}),
    )
    kpi = fixed.kpis[0]
    assert kpi.filter is not None
    assert kpi.filter.column == "status" and kpi.filter.value == "ACTIVE"
    assert not any(w.code == "missing_filter_value" for w in fixed.warnings)


def _spec_with_broken_boolean_filter() -> DashboardSpec:
    kpi = Kpi(kpi_id="kpi_overall_renewal_rate", name="Overall Renewal Rate",
             dataset_id="ds1", operation="count", source_columns=["is_renewed"])
    warning = SpecWarning(code="missing_filter_value", column="is_renewed",
                          detail="kpi kpi_overall_renewal_rate.filter")
    return DashboardSpec(spec_id="s1", dataset_id="ds1", dataset_version="v1",
                         kpis=[kpi], warnings=[warning])


def test_boolean_flag_column_true_synonym_resolves_to_the_real_sample_value() -> None:
    # Regression: a column profiled as boolean carries bare sample_values
    # like ["0", "1"] with no self-describing label. A model reasoning
    # about "Overall Renewal Rate" naturally answers "true" even though the
    # real data encodes that as "1" — a correct answer in substance that a
    # strict verbatim match would previously reject, silently dropping the
    # KPI (and, upstream, several charts) instead of resolving it.
    spec = _spec_with_broken_boolean_filter()
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json(
            {"fills": [{"kpi_id": "kpi_overall_renewal_rate", "field": "filter", "value": "true"}]}),
    )
    kpi = fixed.kpis[0]
    assert kpi.filter is not None
    assert kpi.filter.column == "is_renewed" and kpi.filter.value == "1"
    assert not any(w.code == "missing_filter_value" for w in fixed.warnings)


def test_boolean_flag_column_false_synonym_resolves_to_the_real_sample_value() -> None:
    spec = _spec_with_broken_boolean_filter()
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json(
            {"fills": [{"kpi_id": "kpi_overall_renewal_rate", "field": "filter", "value": "No"}]}),
    )
    kpi = fixed.kpis[0]
    assert kpi.filter is not None and kpi.filter.value == "0"


def test_fill_using_name_key_instead_of_value_is_still_accepted() -> None:
    # Regression, confirmed live against gemini-flash-latest: the original
    # FILTER_REPAIR_SCHEMA left "value" optional and allowed extra
    # properties on each fill item, so the model would satisfy the schema
    # by omitting "value" and adding an unlisted "name" key with the exact
    # same answer instead — every fill then read as an explicit decline
    # (value is None) and the KPI was dropped, even though the model had
    # actually picked a correct, real sample_value.
    spec = _spec_with_broken_filter()
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json(
            {"fills": [{"kpi_id": "kpi_active_count", "field": "filter", "name": "ACTIVE"}]}),
    )
    kpi = fixed.kpis[0]
    assert kpi.filter is not None and kpi.filter.value == "ACTIVE"
    assert not any(w.code == "missing_filter_value" for w in fixed.warnings)


def test_non_boolean_column_is_unaffected_by_boolean_normalization() -> None:
    # "active" vs "ACTIVE" is a case mismatch on a genuine categorical
    # column (not a boolean pair) — must still be rejected, never coerced.
    spec = _spec_with_broken_filter()
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json(
            {"fills": [{"kpi_id": "kpi_active_count", "field": "filter", "value": "active"}]}),
    )
    assert fixed.kpis == []
    assert any(w.code == "dropped_unresolvable_kpi" for w in fixed.warnings)


def test_declines_to_invent_a_value_not_in_sample_values_and_drops_the_kpi() -> None:
    # Confirmed live: gemini-flash-latest correctly returns null rather than
    # guess when no real sample_value semantically fits. Whatever the reason
    # a value can't be verified, leaving the KPI with filter=None would be
    # unsafe (an unfiltered count masquerading as a filtered one) — so the
    # whole KPI is dropped instead, never left half-fixed.
    spec = _spec_with_broken_filter()
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json(
            {"fills": [{"kpi_id": "kpi_active_count", "field": "filter", "value": "active"}]}),
    )  # wrong case — must not match verbatim
    assert fixed.kpis == []
    assert not any(w.code == "missing_filter_value" for w in fixed.warnings)
    assert any(w.code == "dropped_unresolvable_kpi" and w.column == "status" for w in fixed.warnings)


def test_model_declining_with_null_drops_the_kpi() -> None:
    spec = _spec_with_broken_filter()
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json(
            {"fills": [{"kpi_id": "kpi_active_count", "field": "filter", "value": None}]}),
    )
    assert fixed.kpis == []
    assert not any(w.code == "missing_filter_value" for w in fixed.warnings)
    assert any(w.code == "dropped_unresolvable_kpi" for w in fixed.warnings)


# ── repair_missing_filters — numerator/denominator ──────────────────────

def test_repairs_a_numerator_filter() -> None:
    spec = _spec_with_broken_ratio_filter()
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json(
            {"fills": [{"kpi_id": "kpi_renewal_rate", "field": "numerator", "value": "Renewed"}]}),
    )
    kpi = fixed.kpis[0]
    assert kpi.numerator is not None and kpi.numerator.filter is not None
    assert kpi.numerator.filter.value == "Renewed"
    # Denominator's own (already-valid) filter must survive untouched.
    assert kpi.denominator is not None and kpi.denominator.filter.values == ["Renewed", "Not Renewed"]
    assert not any(w.code == "missing_filter_value" for w in fixed.warnings)


def test_mixed_batch_keeps_the_resolved_kpi_and_drops_only_the_unresolved_one() -> None:
    resolvable = Kpi(kpi_id="kpi_active_count", name="Active Contracts Count",
                     dataset_id="ds1", operation="count", source_columns=["status"])
    unresolvable = Kpi(kpi_id="kpi_renewal_rate", name="Renewal Rate", dataset_id="ds1",
                       operation="percentage", zero_denominator_policy="return_null_with_warning",
                       numerator=KpiOperand(operation="count"),
                       denominator=KpiOperand(operation="count",
                                              filter=KpiFilter(column="renewal_status",
                                                               values=["Renewed", "Not Renewed"])))
    spec = DashboardSpec(
        spec_id="s1", dataset_id="ds1", dataset_version="v1",
        kpis=[resolvable, unresolvable],
        warnings=[
            SpecWarning(code="missing_filter_value", column="status",
                       detail="kpi kpi_active_count.filter"),
            SpecWarning(code="missing_filter_value", column="renewal_status",
                       detail="kpi kpi_renewal_rate.numerator.filter"),
        ])
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json({"fills": [
            {"kpi_id": "kpi_active_count", "field": "filter", "value": "ACTIVE"},
            {"kpi_id": "kpi_renewal_rate", "field": "numerator", "value": None},
        ]}),
    )
    remaining_ids = {k.kpi_id for k in fixed.kpis}
    assert remaining_ids == {"kpi_active_count"}
    assert fixed.kpis[0].filter is not None and fixed.kpis[0].filter.value == "ACTIVE"
    assert not any(w.code == "missing_filter_value" for w in fixed.warnings)
    assert any(w.code == "dropped_unresolvable_kpi" for w in fixed.warnings)


# ── cascade: dropping a KPI must not leave dangling dependents ───────────
#
# Regression, found live: dropping an unresolvable KPI used to leave any
# Analysis whose `metric` pointed at it, and any Visualization whose
# `source_ref` pointed at either, completely untouched. The dangling
# reference then surfaced several stages later, at C14 dashboard
# composition, as "chart_type_mismatch: kpi_card must bind to a kpi_id" —
# a confusing symptom nowhere near this, its real cause.

def test_dropping_a_kpi_also_drops_the_analysis_that_pointed_at_it() -> None:
    spec = _spec_with_broken_filter()  # drops kpi_active_count below
    spec = spec.model_copy(update={"analyses": [
        Analysis(analysis_id="an_active_by_region", operation="group_by",
                 group_by=["region"], metric="kpi_active_count"),
        Analysis(analysis_id="an_unrelated", operation="group_by",
                 group_by=["region"], metric="kpi_other"),
    ]})
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json({"fills": [
            {"kpi_id": "kpi_active_count", "field": "filter", "value": None}]}),
    )
    assert fixed.kpis == []
    remaining_analysis_ids = {a.analysis_id for a in fixed.analyses}
    assert remaining_analysis_ids == {"an_unrelated"}
    assert any(w.code == "dropped_dangling_analysis" and "an_active_by_region" in w.detail
              for w in fixed.warnings)


def test_dropping_a_kpi_also_drops_a_kpi_card_bound_to_it_directly() -> None:
    spec = _spec_with_broken_filter()
    spec = spec.model_copy(update={"visualizations": [
        Visualization(chart_id="viz_active_card", chart_type="kpi_card",
                     source_ref="kpi_active_count"),
        Visualization(chart_id="viz_unrelated", chart_type="kpi_card", source_ref="kpi_other"),
    ]})
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json({"fills": [
            {"kpi_id": "kpi_active_count", "field": "filter", "value": None}]}),
    )
    remaining_chart_ids = {v.chart_id for v in fixed.visualizations}
    assert remaining_chart_ids == {"viz_unrelated"}
    assert any(w.code == "dropped_dangling_visualization" and "viz_active_card" in w.detail
              for w in fixed.warnings)


def test_dropping_a_kpi_cascades_through_its_analysis_to_a_chart() -> None:
    # Two-hop cascade: KPI -> Analysis (metric) -> Visualization (source_ref).
    spec = _spec_with_broken_filter()
    spec = spec.model_copy(update={
        "analyses": [Analysis(analysis_id="an_active_by_region", operation="group_by",
                              group_by=["region"], metric="kpi_active_count")],
        "visualizations": [Visualization(chart_id="viz_active_bar", chart_type="bar",
                                         source_ref="an_active_by_region")],
    })
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json({"fills": [
            {"kpi_id": "kpi_active_count", "field": "filter", "value": None}]}),
    )
    assert fixed.analyses == []
    assert fixed.visualizations == []
    assert any(w.code == "dropped_dangling_analysis" for w in fixed.warnings)
    assert any(w.code == "dropped_dangling_visualization" and "viz_active_bar" in w.detail
              for w in fixed.warnings)


def test_a_resolved_kpi_never_cascades_and_drops_nothing() -> None:
    spec = _spec_with_broken_filter()
    spec = spec.model_copy(update={
        "analyses": [Analysis(analysis_id="an_active_by_region", operation="group_by",
                              group_by=["region"], metric="kpi_active_count")],
        "visualizations": [Visualization(chart_id="viz_active_bar", chart_type="bar",
                                         source_ref="an_active_by_region")],
    })
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json({"fills": [
            {"kpi_id": "kpi_active_count", "field": "filter", "value": "ACTIVE"}]}),
    )
    assert [k.kpi_id for k in fixed.kpis] == ["kpi_active_count"]
    assert [a.analysis_id for a in fixed.analyses] == ["an_active_by_region"]
    assert [v.chart_id for v in fixed.visualizations] == ["viz_active_bar"]
    assert not any(w.code in ("dropped_dangling_analysis", "dropped_dangling_visualization")
                  for w in fixed.warnings)


# ── safety / no-op paths ─────────────────────────────────────────────────

def test_noop_when_no_missing_filter_value_warnings() -> None:
    spec = DashboardSpec(spec_id="s1", dataset_id="ds1", dataset_version="v1",
                         kpis=[Kpi(kpi_id="k1", operation="count")])
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json({"fills": []}))
    assert fixed is spec  # never even calls the LLM


def test_drops_the_kpi_when_column_has_no_sample_values_at_all() -> None:
    # Nothing real to offer the model at all — never even calls the LLM
    # (the fake raises if it's invoked), but still can't leave the KPI
    # half-filtered, so it's dropped the same way an unresolved LLM answer
    # would be.
    kpi = Kpi(kpi_id="kpi_x", dataset_id="ds1", operation="count", source_columns=["notes"])
    warning = SpecWarning(code="missing_filter_value", column="notes", detail="kpi kpi_x.filter")
    spec = DashboardSpec(spec_id="s1", dataset_id="ds1", dataset_version="v1",
                         kpis=[kpi], warnings=[warning])

    def _must_not_be_called(broker, tier, system, user, schema):
        raise AssertionError("complete_json_fn should not be called with no sample_values to offer")

    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=[{"name": "notes", "type": "text", "sample_values": []}],
        broker=_FakeBroker(), tier="frontier", complete_json_fn=_must_not_be_called)
    assert fixed.kpis == []
    assert any(w.code == "dropped_unresolvable_kpi" for w in fixed.warnings)


def test_never_raises_on_malformed_llm_response_and_drops_the_kpi() -> None:
    # A malformed response resolves nothing, same as an explicit null — the
    # KPI still can't be trusted with filter=None, so it's dropped, never a
    # crash and never a silently-wrong unfiltered count.
    spec = _spec_with_broken_filter()
    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json({"not_fills": "garbage"}))
    assert fixed.kpis == []
    assert any(w.code == "dropped_unresolvable_kpi" for w in fixed.warnings)


def test_never_raises_when_complete_json_fn_raises_and_drops_the_kpi() -> None:
    spec = _spec_with_broken_filter()

    def _boom(broker, tier, system, user, schema):
        raise RuntimeError("provider down")

    fixed = repair_missing_filters(
        spec, objective="x", approved_columns=APPROVED_COLUMNS,
        broker=_FakeBroker(), tier="frontier", complete_json_fn=_boom)
    assert fixed.kpis == []
    assert any(w.code == "dropped_unresolvable_kpi" for w in fixed.warnings)


# ── workspace mode (columns_by_dataset, not a flat list) ────────────────

def test_workspace_mode_looks_up_samples_by_the_kpis_own_dataset() -> None:
    spec = _spec_with_broken_filter()  # kpi.dataset_id == "ds1"
    fixed = repair_missing_filters(
        spec, objective="x",
        columns_by_dataset={"ds1": APPROVED_COLUMNS, "ds2": []},
        broker=_FakeBroker(), tier="frontier",
        complete_json_fn=_fake_complete_json(
            {"fills": [{"kpi_id": "kpi_active_count", "field": "filter", "value": "ACTIVE"}]}),
    )
    assert fixed.kpis[0].filter is not None and fixed.kpis[0].filter.value == "ACTIVE"


def test_workspace_mode_wrong_dataset_has_no_samples_so_the_kpi_is_dropped() -> None:
    spec = _spec_with_broken_filter()  # kpi.dataset_id == "ds1"

    def _must_not_be_called(broker, tier, system, user, schema):
        raise AssertionError("complete_json_fn should not be called with no sample_values to offer")

    fixed = repair_missing_filters(
        spec, objective="x",
        columns_by_dataset={"ds2": APPROVED_COLUMNS},  # "ds1" (the KPI's own) has nothing
        broker=_FakeBroker(), tier="frontier", complete_json_fn=_must_not_be_called)
    assert fixed.kpis == []
    assert any(w.code == "dropped_unresolvable_kpi" for w in fixed.warnings)
