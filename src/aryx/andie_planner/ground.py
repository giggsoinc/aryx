"""Deterministic grounding validator (C08) — the real "no invention" gate.

The LLM's JSON is NEVER trusted directly. Every column, operation, chart type,
and cross-reference (kpi_id/analysis_id) is checked here against the actual
planning_context; anything unsupported is stripped and recorded as a warning,
never silently dropped and never replaced with an invented substitute.

Pure and deterministic — no LLM call, no I/O. Fully unit-testable with a hand
built `raw` dict.
"""
from __future__ import annotations

from typing import Any

from aryx.andie_planner.models import (
    Analysis,
    Assumption,
    BusinessQuestion,
    DashboardSpec,
    DeltaSpecItems,
    Kpi,
    KpiFilter,
    KpiOperand,
    SpecWarning,
    Visualization,
)

_QUESTION_RANGE = (3, 5)


def _as_str(value: Any) -> str | None:
    """Coerce to str only if it already IS a string; else drop (never guess).

    Small local models occasionally emit the wrong JSON type for a string
    field (e.g. `false` instead of a policy name) — silently stringifying that
    would invent content; dropping it and recording a warning is safer and
    matches "no invention". This is what actually prevents a malformed type
    from crashing Pydantic validation deep inside DashboardSpec construction.
    """
    return value if isinstance(value, str) and value.strip() else None


def _as_filter(raw: Any, approved_cols: set[str], warnings: list[SpecWarning],
              where: str) -> KpiFilter | None:
    if not isinstance(raw, dict):
        return None
    col = _as_str(raw.get("column"))
    if col is None:
        return None
    if col not in approved_cols:
        warnings.append(SpecWarning(code="unapproved_column", column=col,
                                    detail=f"{where}.filter"))
        return None
    value, values = raw.get("value"), raw.get("values")
    if value is None and not values:
        # A filter with a column but no value/values is structurally valid
        # (KpiFilter.value/values are both optional) but semantically empty:
        # compiled as filter_equals(column, None), it matches rows where the
        # column is actually null — typically zero — silently zeroing out
        # whatever KPI/analysis depends on it instead of failing loudly.
        warnings.append(SpecWarning(code="missing_filter_value", column=col,
                                    detail=f"{where}.filter"))
        return None
    return KpiFilter(column=col, operator=_as_str(raw.get("operator")) or "equals",
                     value=value, values=values)


def _as_operand(raw: Any, approved_cols: set[str], approved_ops: set[str],
                warnings: list[SpecWarning], where: str) -> KpiOperand | None:
    if not isinstance(raw, dict):
        return None
    op = _as_str(raw.get("operation"))
    if op is None:
        return None
    if op not in approved_ops:
        warnings.append(SpecWarning(code="unsupported_operation",
                                    detail=f"{where}: {op}"))
        return None
    return KpiOperand(operation=op,
                      filter=_as_filter(raw.get("filter"), approved_cols, warnings, where))


def _ground_kpi(raw: dict, approved_cols: set[str], approved_ops: set[str],
               warnings: list[SpecWarning], dataset_id: str = "") -> Kpi | None:
    kid = _as_str(raw.get("kpi_id"))
    op = _as_str(raw.get("operation"))
    if kid is None:
        return None
    if op is None or op not in approved_ops:
        warnings.append(SpecWarning(code="unsupported_operation",
                                    detail=f"kpi {kid}: {op!r}"))
        return None
    src_cols = [c for c in (raw.get("source_columns") or []) if isinstance(c, str)]
    bad = [c for c in src_cols if c not in approved_cols]
    for c in bad:
        # One warning PER invented column (not one warning listing all of
        # them) — column=c makes the exact invented name available to C09's
        # repair-request builder, instead of only a stringified list.
        warnings.append(SpecWarning(code="unapproved_column", column=c,
                                    detail=f"kpi {kid}.source_columns"))
    good_cols = [c for c in src_cols if c in approved_cols]

    measure = _as_str(raw.get("measure"))
    if measure is not None and measure not in approved_cols:
        warnings.append(SpecWarning(code="unapproved_column", column=measure,
                                    detail=f"kpi {kid}.measure"))
        measure = None

    zero_policy = _as_str(raw.get("zero_denominator_policy"))
    if raw.get("zero_denominator_policy") is not None and zero_policy is None:
        warnings.append(SpecWarning(code="bad_field_type",
                                    detail=f"kpi {kid}.zero_denominator_policy"))

    return Kpi(
        kpi_id=kid, name=_as_str(raw.get("name")) or kid, dataset_id=dataset_id,
        source_columns=good_cols, operation=op, measure=measure,
        filter=_as_filter(raw.get("filter"), approved_cols, warnings, f"kpi {kid}"),
        numerator=_as_operand(raw.get("numerator"), approved_cols, approved_ops,
                              warnings, f"kpi {kid}.numerator"),
        denominator=_as_operand(raw.get("denominator"), approved_cols, approved_ops,
                                warnings, f"kpi {kid}.denominator"),
        zero_denominator_policy=zero_policy,
        format=_as_str(raw.get("format")) or "number",
    )


def _ground_analysis(raw: dict, approved_cols: set[str], approved_ops: set[str],
                     valid_kpi_ids: set[str], warnings: list[SpecWarning],
                     dataset_id: str = "",
                     approved_graph_paths: frozenset[str] = frozenset()) -> Analysis | None:
    aid = _as_str(raw.get("analysis_id"))
    op = _as_str(raw.get("operation"))
    if aid is None:
        return None
    if op is None or op not in approved_ops:
        warnings.append(SpecWarning(code="unsupported_operation",
                                    detail=f"analysis {aid}: {op!r}"))
        return None
    graph_path_id = _as_str(raw.get("graph_path_id"))
    if op == "graph_relation":
        # No dataset columns involved — the graph query IS the lineage, so
        # this is the one operation grounded against approved_graph_paths
        # instead of approved_cols.
        if graph_path_id is None or graph_path_id not in approved_graph_paths:
            warnings.append(SpecWarning(code="invalid_graph_path",
                                        detail=f"analysis {aid}: {graph_path_id!r}"))
            return None
        return Analysis(analysis_id=aid, operation=op, dataset_id=dataset_id,
                        graph_path_id=graph_path_id)
    requested = [c for c in (raw.get("group_by") or []) if isinstance(c, str)]
    bad = [c for c in requested if c not in approved_cols]
    for c in bad:
        # One warning PER invented column — see _ground_kpi for why.
        warnings.append(SpecWarning(code="unapproved_column", column=c,
                                    detail=f"analysis {aid}.group_by"))
    group_by = [c for c in requested if c in approved_cols]

    metric = _as_str(raw.get("metric"))
    if metric is not None and metric not in valid_kpi_ids:
        warnings.append(SpecWarning(code="dangling_reference",
                                    detail=f"analysis {aid}.metric -> {metric!r}"))
        metric = None

    def _ground_col(field: str) -> str | None:
        col = _as_str(raw.get(field))
        if col is None:
            return None
        if col not in approved_cols:
            warnings.append(SpecWarning(code="unapproved_column", column=col,
                                        detail=f"analysis {aid}.{field}"))
            return None
        return col

    return Analysis(
        analysis_id=aid, operation=op, dataset_id=dataset_id,
        group_by=group_by, metric=metric, sort=_as_str(raw.get("sort")),
        x_column=_ground_col("x_column"), y_column=_ground_col("y_column"),
        size_column=_ground_col("size_column"),
        start_column=_ground_col("start_column"), end_column=_ground_col("end_column"))


def _ground_visualization(raw: dict, approved_cols: set[str], approved_charts: set[str],
                          valid_refs: set[str],
                          warnings: list[SpecWarning]) -> Visualization | None:
    cid = _as_str(raw.get("chart_id"))
    ctype = _as_str(raw.get("chart_type"))
    ref = _as_str(raw.get("source_ref"))
    if cid is None:
        return None
    if ctype is None or ctype not in approved_charts:
        warnings.append(SpecWarning(code="unsupported_chart_type",
                                    detail=f"{cid}: {ctype!r}"))
        return None
    if ref is None or ref not in valid_refs:
        warnings.append(SpecWarning(code="dangling_reference",
                                    detail=f"{cid}.source_ref -> {ref!r}"))
        return None
    x_axis = _as_str(raw.get("x_axis"))
    if x_axis is not None and x_axis not in approved_cols and x_axis not in valid_refs:
        warnings.append(SpecWarning(code="unapproved_column", column=x_axis,
                                    detail=f"{cid}.x_axis"))
        x_axis = None
    compare_ref = _as_str(raw.get("compare_ref"))
    if compare_ref is not None and compare_ref not in valid_refs:
        warnings.append(SpecWarning(code="dangling_reference",
                                    detail=f"{cid}.compare_ref -> {compare_ref!r}"))
        compare_ref = None
    axis_refs: list[str] | None = None
    raw_axis_refs = raw.get("axis_refs")
    if isinstance(raw_axis_refs, list):
        kept = []
        for a in raw_axis_refs:
            a = _as_str(a)
            if a is None:
                continue
            if a not in valid_refs:
                warnings.append(SpecWarning(code="dangling_reference",
                                            detail=f"{cid}.axis_refs -> {a!r}"))
                continue
            kept.append(a)
        axis_refs = kept or None
    return Visualization(chart_id=cid, chart_type=ctype, source_ref=ref,
                         x_axis=x_axis, y_axis=_as_str(raw.get("y_axis")),
                         compare_ref=compare_ref, axis_refs=axis_refs)


def ground_spec(
    raw: dict,
    *,
    dataset_id: str,
    dataset_version: str,
    approved_columns: list[dict[str, str]],
    approved_operations: list[str],
    approved_charts: list[str],
    approved_graph_paths: list[str] | None = None,
    datasets: list[dict[str, Any]] | None = None,
    objective: str = "",
    target_audience: str = "",
    output_schema_version: str = "dashboard_spec_v1",
    model_name: str = "",
    model_tier: str = "",
    prompt_version: str = "",
) -> DashboardSpec:
    """Rebuild a grounded DashboardSpec from raw LLM JSON.

    Every reference is checked against the approved resources given here; a
    column/operation/chart/cross-reference that isn't approved is dropped and
    recorded in `warnings` — never invented, never silently ignored.

    Args:
        datasets: Workspace-scope only — [{"dataset_id", "approved_columns"},
            ...] grouped per source dataset (see planning.models.DatasetColumns).
            When given, every KPI/analysis must declare its OWN `dataset_id`
            and is validated against THAT dataset's columns, never a flattened
            union — column names collide across unrelated datasets often
            enough (verified: 25 of 65 names in one 21-dataset workspace) that
            a flat check would let a KPI silently reference the wrong table's
            column. None (the default) preserves single-dataset behavior
            exactly, validating against the flat `approved_columns`.
    """
    approved_cols = {c["name"] for c in approved_columns if c.get("name")}
    approved_ops = set(approved_operations)
    approved_charts_set = set(approved_charts)
    approved_graph_paths_set = frozenset(approved_graph_paths or [])
    warnings: list[SpecWarning] = []

    cols_by_dataset: dict[str, set[str]] | None = None
    if datasets is not None:
        cols_by_dataset = {
            d["dataset_id"]: {c["name"] for c in d.get("approved_columns", []) if c.get("name")}
            for d in datasets if d.get("dataset_id")
        }
        # x_axis/y_axis are cosmetic display fields, not join/scope keys —
        # checked against the union across all datasets rather than needing
        # their own explicit dataset_id (visualizations don't have one).
        approved_cols = set().union(*cols_by_dataset.values()) if cols_by_dataset else set()

    questions: list[BusinessQuestion] = []
    for i, q in enumerate(raw.get("business_questions") or []):
        if not isinstance(q, dict):
            continue
        text = _as_str(q.get("text"))
        if text:
            questions.append(BusinessQuestion(
                question_id=_as_str(q.get("question_id")) or f"bq_{i + 1:03d}", text=text))
    lo, hi = _QUESTION_RANGE
    if not (lo <= len(questions) <= hi):
        warnings.append(SpecWarning(
            code="question_count_out_of_range",
            detail=f"{len(questions)} questions (expected {lo}-{hi})"))

    kpis: list[Kpi] = []
    for k in raw.get("kpis") or []:
        if not isinstance(k, dict):
            continue
        if cols_by_dataset is not None:
            kd = _as_str(k.get("dataset_id"))
            if kd is None or kd not in cols_by_dataset:
                warnings.append(SpecWarning(code="unknown_dataset",
                                            detail=f"kpi {k.get('kpi_id')!r}: dataset_id={kd!r}"))
                continue
            item_cols = cols_by_dataset[kd]
        else:
            kd, item_cols = dataset_id, approved_cols
        kpi = _ground_kpi(k, item_cols, approved_ops, warnings, dataset_id=kd)
        if kpi is not None:
            kpis.append(kpi)
    valid_kpi_ids = {k.kpi_id for k in kpis}

    analyses: list[Analysis] = []
    for a in raw.get("analyses") or []:
        if not isinstance(a, dict):
            continue
        is_graph_relation = _as_str(a.get("operation")) == "graph_relation"
        if cols_by_dataset is not None:
            if is_graph_relation:
                # Spans the whole workspace graph, not one dataset — never
                # gated on dataset_id the way every other operation is.
                ad, item_cols = "", set()
            else:
                ad = _as_str(a.get("dataset_id"))
                if ad is None or ad not in cols_by_dataset:
                    warnings.append(SpecWarning(
                        code="unknown_dataset",
                        detail=f"analysis {a.get('analysis_id')!r}: dataset_id={ad!r}"))
                    continue
                item_cols = cols_by_dataset[ad]
        else:
            ad, item_cols = dataset_id, approved_cols
        analysis = _ground_analysis(a, item_cols, approved_ops, valid_kpi_ids, warnings,
                                    dataset_id=ad, approved_graph_paths=approved_graph_paths_set)
        if analysis is not None:
            analyses.append(analysis)
    valid_refs = valid_kpi_ids | {a.analysis_id for a in analyses}

    visualizations: list[Visualization] = []
    for v in raw.get("visualizations") or []:
        if not isinstance(v, dict):
            continue
        viz = _ground_visualization(v, approved_cols, approved_charts_set, valid_refs, warnings)
        if viz is not None:
            visualizations.append(viz)

    assumptions: list[Assumption] = []
    for a in raw.get("assumptions") or []:
        if not isinstance(a, dict):
            continue
        code = _as_str(a.get("code"))
        if code:
            assumptions.append(Assumption(code=code, meaning=_as_str(a.get("meaning")) or ""))

    for w in raw.get("warnings") or []:
        if not isinstance(w, dict):
            continue
        code = _as_str(w.get("code"))
        if code:
            warnings.append(SpecWarning(code=code, column=_as_str(w.get("column")) or "",
                                        detail=_as_str(w.get("detail")) or ""))

    status = "valid" if (questions and kpis) else "invalid"
    return DashboardSpec(
        spec_id=f"dashboard_spec_{dataset_id}_{dataset_version}",
        dataset_id=dataset_id, dataset_version=dataset_version,
        output_schema_version=output_schema_version,
        objective=objective, target_audience=target_audience,
        business_questions=questions, kpis=kpis, analyses=analyses,
        visualizations=visualizations, assumptions=assumptions, warnings=warnings,
        spec_status=status, model_name=model_name, model_tier=model_tier,
        prompt_version=prompt_version,
    )


def _dedupe_id(candidate: str, existing: set[str]) -> str:
    """Deterministically disambiguate an id the model reused from the spec
    it's extending — e.g. the model drafts "chart1" again, colliding with an
    ALREADY-PERSISTED "chart1" from the batch plan. This is id bookkeeping,
    not content invention: the same rename any two humans would make by hand
    to avoid a collision, never a change to what the id refers to."""
    if candidate not in existing:
        return candidate
    n = 2
    while f"{candidate}_{n}" in existing:
        n += 1
    return f"{candidate}_{n}"


def ground_delta(
    raw: dict,
    *,
    existing_kpi_ids: set[str],
    existing_analysis_ids: set[str],
    existing_chart_ids: set[str],
    approved_columns: list[dict[str, str]],
    approved_operations: list[str],
    approved_charts: list[str],
    approved_graph_paths: list[str] | None = None,
    datasets: list[dict[str, Any]] | None = None,
    dataset_id: str = "",
) -> DeltaSpecItems:
    """Rebuild a grounded DeltaSpecItems from raw LLM JSON — the exact same
    "no invention" gate as `ground_spec`, scoped to one ask-to-visualize
    request instead of a whole spec. Reuses `_ground_kpi`/`_ground_analysis`/
    `_ground_visualization` unchanged.

    `existing_kpi_ids`/`existing_analysis_ids` are the spec-being-extended's
    own ids — a new analysis's `metric` may cite any existing OR newly
    drafted kpi_id; a new visualization's `source_ref`/`compare_ref`/
    `axis_refs` may cite any existing OR newly drafted kpi_id/analysis_id.
    Any newly drafted kpi_id/analysis_id/chart_id that collides with one of
    these (the model re-using e.g. "chart1") is deterministically
    disambiguated via `_dedupe_id`, never silently merged into/overwriting
    the existing item of the same id.

    `datasets` mirrors `ground_spec`'s workspace-scope mode: when given, a
    drafted new_kpi/new_analysis must declare its own `dataset_id` and is
    checked against THAT dataset's columns only, never a flattened union.
    """
    approved_ops = set(approved_operations)
    approved_charts_set = set(approved_charts)
    approved_graph_paths_set = frozenset(approved_graph_paths or [])
    warnings: list[SpecWarning] = []

    cols_by_dataset: dict[str, set[str]] | None = None
    approved_cols = {c["name"] for c in approved_columns if c.get("name")}
    if datasets is not None:
        cols_by_dataset = {
            d["dataset_id"]: {c["name"] for c in d.get("approved_columns", []) if c.get("name")}
            for d in datasets if d.get("dataset_id")
        }
        approved_cols = set().union(*cols_by_dataset.values()) if cols_by_dataset else set()

    raw_kpi = raw.get("new_kpi")
    raw_analysis = raw.get("new_analysis")
    raw_viz = raw.get("new_visualization")

    # Disambiguate id collisions with the spec being extended BEFORE
    # grounding, on the raw dict — renaming AFTER grounding would break the
    # very cross-references (analysis.metric, visualization.source_ref) the
    # rename is trying to preserve. Same "id bookkeeping, not invention"
    # rationale as `_dedupe_id` itself.
    def _retarget_viz_refs(viz: dict | None, old_id: str, new_id: str) -> dict | None:
        if not isinstance(viz, dict):
            return viz
        updated = dict(viz)
        if updated.get("source_ref") == old_id:
            updated["source_ref"] = new_id
        if updated.get("compare_ref") == old_id:
            updated["compare_ref"] = new_id
        axis_refs = updated.get("axis_refs")
        if isinstance(axis_refs, list) and old_id in axis_refs:
            updated["axis_refs"] = [new_id if a == old_id else a for a in axis_refs]
        return updated

    id_namespace = set(existing_kpi_ids) | set(existing_analysis_ids)
    if isinstance(raw_kpi, dict) and isinstance(raw_kpi.get("kpi_id"), str):
        old_id = raw_kpi["kpi_id"]
        new_id = _dedupe_id(old_id, id_namespace)
        if new_id != old_id:
            raw_kpi = {**raw_kpi, "kpi_id": new_id}
            id_namespace = id_namespace | {new_id}
            if isinstance(raw_analysis, dict) and raw_analysis.get("metric") == old_id:
                raw_analysis = {**raw_analysis, "metric": new_id}
            raw_viz = _retarget_viz_refs(raw_viz, old_id, new_id)
    if isinstance(raw_analysis, dict) and isinstance(raw_analysis.get("analysis_id"), str):
        old_id = raw_analysis["analysis_id"]
        new_id = _dedupe_id(old_id, id_namespace)
        if new_id != old_id:
            raw_analysis = {**raw_analysis, "analysis_id": new_id}
            id_namespace = id_namespace | {new_id}
            raw_viz = _retarget_viz_refs(raw_viz, old_id, new_id)
    if isinstance(raw_viz, dict) and isinstance(raw_viz.get("chart_id"), str):
        raw_viz = {**raw_viz, "chart_id": _dedupe_id(raw_viz["chart_id"], set(existing_chart_ids))}

    new_kpi: Kpi | None = None
    if isinstance(raw_kpi, dict) and raw_kpi:
        if cols_by_dataset is not None:
            kd = _as_str(raw_kpi.get("dataset_id"))
            if kd is not None and kd in cols_by_dataset:
                new_kpi = _ground_kpi(raw_kpi, cols_by_dataset[kd], approved_ops, warnings, dataset_id=kd)
            else:
                warnings.append(SpecWarning(code="unknown_dataset", detail=f"new_kpi: dataset_id={kd!r}"))
        else:
            new_kpi = _ground_kpi(raw_kpi, approved_cols, approved_ops, warnings, dataset_id=dataset_id)

    valid_kpi_ids = set(existing_kpi_ids)
    if new_kpi is not None:
        valid_kpi_ids.add(new_kpi.kpi_id)

    new_analysis: Analysis | None = None
    if isinstance(raw_analysis, dict) and raw_analysis:
        is_graph_relation = _as_str(raw_analysis.get("operation")) == "graph_relation"
        if cols_by_dataset is not None and not is_graph_relation:
            ad = _as_str(raw_analysis.get("dataset_id"))
            if ad is not None and ad in cols_by_dataset:
                new_analysis = _ground_analysis(raw_analysis, cols_by_dataset[ad], approved_ops,
                                                valid_kpi_ids, warnings, dataset_id=ad,
                                                approved_graph_paths=approved_graph_paths_set)
            else:
                warnings.append(SpecWarning(code="unknown_dataset",
                                            detail=f"new_analysis: dataset_id={ad!r}"))
        else:
            new_analysis = _ground_analysis(
                raw_analysis, approved_cols, approved_ops, valid_kpi_ids, warnings,
                dataset_id="" if is_graph_relation else dataset_id,
                approved_graph_paths=approved_graph_paths_set)

    valid_refs = valid_kpi_ids | set(existing_analysis_ids)
    if new_analysis is not None:
        valid_refs.add(new_analysis.analysis_id)

    new_visualization: Visualization | None = None
    if isinstance(raw_viz, dict) and raw_viz:
        new_visualization = _ground_visualization(raw_viz, approved_cols, approved_charts_set,
                                                   valid_refs, warnings)

    for w in raw.get("warnings") or []:
        if not isinstance(w, dict):
            continue
        code = _as_str(w.get("code"))
        if code:
            warnings.append(SpecWarning(code=code, column=_as_str(w.get("column")) or "",
                                        detail=_as_str(w.get("detail")) or ""))

    return DeltaSpecItems(new_kpi=new_kpi, new_analysis=new_analysis,
                          new_visualization=new_visualization, warnings=warnings)
