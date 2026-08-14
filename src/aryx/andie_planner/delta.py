"""Ask-to-visualize (C08 extension): draft, ground, and confirm ONE new
chart against an already-approved DashboardSpec — never a full re-plan.

Two-step flow:
  1. `draft_delta` — one narrow LLM call + grounding + a READ-ONLY validation
     check against a merged-but-not-persisted spec, so the caller can show a
     preview ("this will work" / "this was rejected: ...") before anything
     is written. Never persists, never chains execution/composition.
  2. `confirm_delta` — refetches the CURRENT latest spec (never trusts a
     stale draft), re-merges, RE-VALIDATES (the actual safety net — a
     client-echoed payload is never trusted blindly), persists, then chains
     the exact same C10->C11->C12->C13->C14 steps `run_planner` already
     uses. One call, the chart appears.

Both steps reuse the batch pipeline's own machinery unchanged (ground.py's
per-item helpers via `ground_delta`, spec_validation.validate_spec,
andie_planner.run's C10/C11 chaining, analysis_execution.run_analysis_execution,
dashboard_composition.compose_dashboard) — the only genuinely new code here
is the narrower prompt/grounding for one item and the merge-into-spec step.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from aryx.analysis_execution.run import run_analysis_execution
from aryx.andie_planner.ground import _dedupe_id, ground_delta
from aryx.andie_planner.models import DashboardSpec, DeltaDraftResult, DeltaSpecItems, PlannerResult
from aryx.andie_planner.prompt import append_repair_constraints, build_delta_prompt
from aryx.andie_planner.run import _run_c10_for_approved, _single_dataset_ctx, _workspace_ctx
from aryx.andie_planner.schema import DELTA_SPEC_SCHEMA
from aryx.dashboard_composition.run import compose_dashboard
from aryx.spec_validation.checks import ValidationContext
from aryx.spec_validation.validate import repair_constraints_text, validate_spec
from aryx.store.context_store import ContextStore
from aryx.store.dashboard_spec_store import DashboardSpecStore

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2  # one real attempt + one malformed-JSON retry, same as generate.py

CompleteJsonFn = Callable[[Any, str, str, str, dict], dict]


def _is_malformed_delta(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return True
    return not any(k in raw for k in ("new_kpi", "new_analysis", "new_visualization", "warnings"))


def _run_delta_llm_loop(
    system: str, user: str, broker: Any, tier: str, complete_json_fn: CompleteJsonFn,
) -> tuple[dict | None, DeltaDraftResult | None, int]:
    """Retry-once-then-controlled-error, same state machine as
    generate.py's `_run_llm_loop`, with a delta-shaped malformed check."""
    raw: dict = {}
    last_error = ""
    attempt = 0
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            raw = complete_json_fn(broker, tier, system, user, DELTA_SPEC_SCHEMA)
        except Exception as exc:  # noqa: BLE001 — broker/provider failure
            last_error = str(exc)
            logger.warning("ask_to_visualize llm call failed attempt=%d: %s", attempt, exc)
            if attempt >= _MAX_ATTEMPTS:
                return None, DeltaDraftResult(status="controlled_error", error_code="llm_call_failed",
                                              error_message=last_error, attempts=attempt), attempt
            continue
        if _is_malformed_delta(raw):
            last_error = "model returned none of new_kpi/new_analysis/new_visualization/warnings"
            logger.warning("ask_to_visualize malformed response attempt=%d", attempt)
            if attempt >= _MAX_ATTEMPTS:
                return None, DeltaDraftResult(status="controlled_error", error_code="malformed_json",
                                              error_message=last_error, attempts=attempt), attempt
            user = (f"{user}\n\nYour previous response was rejected ({last_error}). "
                   "Return ONLY the JSON object with the exact keys requested — "
                   "new_kpi, new_analysis, new_visualization, warnings — no other text.")
            continue
        return raw, None, attempt
    return None, DeltaDraftResult(  # pragma: no cover — loop always returns/breaks above
        status="controlled_error", error_code="malformed_json",
        error_message=last_error, attempts=attempt), attempt


def _merge_spec(existing: DashboardSpec, items: DeltaSpecItems) -> DashboardSpec:
    """Append the drafted item(s) to a COPY of `existing` — never mutates,
    never removes/reorders anything already there."""
    kpis = list(existing.kpis) + ([items.new_kpi] if items.new_kpi is not None else [])
    analyses = list(existing.analyses) + ([items.new_analysis] if items.new_analysis is not None else [])
    visualizations = list(existing.visualizations) + (
        [items.new_visualization] if items.new_visualization is not None else [])
    return existing.model_copy(update={"kpis": kpis, "analyses": analyses, "visualizations": visualizations})


def _preview_text(items: DeltaSpecItems, existing_spec: DashboardSpec) -> str:
    viz = items.new_visualization
    if viz is None:
        if items.warnings:
            w = items.warnings[0]
            return f"Could not draft a chart: {w.detail or w.code}"
        return "Could not draft a chart from that request."
    kpi = items.new_kpi or next((k for k in existing_spec.kpis if k.kpi_id == viz.source_ref), None)
    analysis = items.new_analysis or next(
        (a for a in existing_spec.analyses if a.analysis_id == viz.source_ref), None)
    name = (kpi.name if kpi else None) or (analysis.analysis_id if analysis else viz.source_ref)
    group = f" by {analysis.group_by[0]}" if analysis and analysis.group_by else ""
    return f"New {viz.chart_type} chart: {name}{group}"


def _dedupe_delta_items(items: DeltaSpecItems, existing_spec: DashboardSpec) -> DeltaSpecItems:
    """Same id-collision safety net as `ground_delta`, applied a second time
    here since `confirm_delta` receives already-typed items straight from
    the client's confirm payload — the spec being extended may have changed
    between draft and confirm, so a collision-free id at draft time is not
    guaranteed to still be collision-free now."""
    new_kpi, new_analysis, new_visualization = items.new_kpi, items.new_analysis, items.new_visualization
    id_namespace = {k.kpi_id for k in existing_spec.kpis} | {a.analysis_id for a in existing_spec.analyses}

    if new_kpi is not None and new_kpi.kpi_id in id_namespace:
        old_id, new_id = new_kpi.kpi_id, _dedupe_id(new_kpi.kpi_id, id_namespace)
        new_kpi = new_kpi.model_copy(update={"kpi_id": new_id})
        id_namespace = id_namespace | {new_id}
        if new_analysis is not None and new_analysis.metric == old_id:
            new_analysis = new_analysis.model_copy(update={"metric": new_id})
        if new_visualization is not None and new_visualization.source_ref == old_id:
            new_visualization = new_visualization.model_copy(update={"source_ref": new_id})

    if new_analysis is not None and new_analysis.analysis_id in id_namespace:
        old_id, new_id = new_analysis.analysis_id, _dedupe_id(new_analysis.analysis_id, id_namespace)
        new_analysis = new_analysis.model_copy(update={"analysis_id": new_id})
        if new_visualization is not None and new_visualization.source_ref == old_id:
            new_visualization = new_visualization.model_copy(update={"source_ref": new_id})

    if new_visualization is not None:
        chart_ids = {v.chart_id for v in existing_spec.visualizations}
        if new_visualization.chart_id in chart_ids:
            new_visualization = new_visualization.model_copy(
                update={"chart_id": _dedupe_id(new_visualization.chart_id, chart_ids)})

    return DeltaSpecItems(new_kpi=new_kpi, new_analysis=new_analysis,
                          new_visualization=new_visualization, warnings=items.warnings)


def _validation_context(planning_context: Any) -> ValidationContext:
    """Single-dataset vs. workspace-scope, same split `run_planner`/
    `run_planner_workspace` already use for C09."""
    if getattr(planning_context, "datasets", None):
        return _workspace_ctx(planning_context)
    return _single_dataset_ctx(planning_context)


def draft_delta(
    existing_spec: DashboardSpec,
    planning_context: Any,
    request_text: str,
    *,
    broker: Any,
    tier: str = "frontier",
    complete_json_fn: CompleteJsonFn,
) -> DeltaDraftResult:
    """Draft, ground, and READ-ONLY-validate one ask-to-visualize request —
    never persists, never chains execution/composition. See module docstring.
    """
    existing_kpis = [
        {"kpi_id": k.kpi_id, "name": k.name, "operation": k.operation, "format": k.format}
        for k in existing_spec.kpis
    ]
    existing_analyses = [
        {"analysis_id": a.analysis_id, "operation": a.operation, "group_by": a.group_by, "metric": a.metric}
        for a in existing_spec.analyses
    ]
    workspace_datasets = list(getattr(planning_context, "datasets", None) or [])
    workspace_mode = bool(workspace_datasets)

    path_hints = [{"path_id": h.path_id, "label": h.label, "depth": h.depth}
                 for h in getattr(planning_context, "graph_path_hints", []) or []]
    quality_notes = list(getattr(planning_context, "graph_quality_notes", []) or [])

    if workspace_mode:
        dataset_groups = [
            {"dataset_id": d.dataset_id,
             "approved_columns": [{"name": c.name, "type": c.type, "sample_values": c.sample_values}
                                  for c in d.approved_columns]}
            for d in workspace_datasets
        ]
        system, user = build_delta_prompt(
            existing_kpis=existing_kpis, existing_analyses=existing_analyses,
            datasets=dataset_groups,
            approved_graph_paths=list(planning_context.approved_graph_paths),
            supported_operations=list(planning_context.supported_operations),
            supported_charts=list(planning_context.supported_charts),
            request_text=request_text, domain=getattr(planning_context, "domain", ""),
            graph_path_hints=path_hints, graph_quality_notes=quality_notes,
        )
    else:
        approved_columns = [
            {"name": c.name, "type": c.type, "sample_values": c.sample_values}
            for c in planning_context.approved_columns
        ]
        dataset_groups = None
        system, user = build_delta_prompt(
            existing_kpis=existing_kpis, existing_analyses=existing_analyses,
            approved_columns=approved_columns,
            approved_graph_paths=list(planning_context.approved_graph_paths),
            supported_operations=list(planning_context.supported_operations),
            supported_charts=list(planning_context.supported_charts),
            request_text=request_text, domain=getattr(planning_context, "domain", ""),
            graph_path_hints=path_hints, graph_quality_notes=quality_notes,
        )

    ctx = _validation_context(planning_context)

    def _ground(raw_json: dict) -> DeltaSpecItems | DeltaDraftResult:
        try:
            return ground_delta(
                raw_json,
                existing_kpi_ids={k.kpi_id for k in existing_spec.kpis},
                existing_analysis_ids={a.analysis_id for a in existing_spec.analyses},
                existing_chart_ids={v.chart_id for v in existing_spec.visualizations},
                approved_columns=[] if workspace_mode else approved_columns,
                approved_operations=list(planning_context.supported_operations),
                approved_charts=list(planning_context.supported_charts),
                approved_graph_paths=list(planning_context.approved_graph_paths),
                datasets=dataset_groups,
                dataset_id=existing_spec.dataset_id,
            )
        except Exception as exc:  # noqa: BLE001 — grounding must never crash the caller
            logger.warning("ask_to_visualize grounding failed: %s", exc, exc_info=True)
            return DeltaDraftResult(status="controlled_error", error_code="grounding_failed",
                                    error_message=str(exc))

    def _validate(candidate_items: DeltaSpecItems, attempt_no: int):
        """Returns (report_or_None, repair_hint_text_or_None). A dropped
        new_visualization has no merged spec to validate — build the repair
        hint directly from ground_delta's own warnings instead, so a
        grounding-level drop (e.g. unsupported_chart_type) gets the same one
        repair chance a validation-level rejection does."""
        if candidate_items.new_visualization is None:
            if not candidate_items.warnings:
                return None, None
            lines = [f"- [{w.code}] {w.detail or w.column}" for w in candidate_items.warnings]
            return None, "\n".join(lines)
        merged = _merge_spec(existing_spec, candidate_items)
        rpt, repair_request = validate_spec(merged, ctx, validation_id=f"delta_{merged.spec_id}",
                                            attempt=attempt_no)
        hint = repair_constraints_text(repair_request) if repair_request is not None else None
        return rpt, hint

    raw, failure, attempt = _run_delta_llm_loop(system, user, broker, tier, complete_json_fn)
    if failure is not None:
        return failure

    items = _ground(raw)
    if isinstance(items, DeltaDraftResult):
        items.attempts = attempt
        return items

    report, repair_hint = _validate(items, 1)

    # One bounded repair retry, same discipline as the batch planner's C09
    # loop (_run_c09_with_bounded_retry): only fired when there's an actual
    # fixable defect to name — never a re-guess from scratch, never more
    # than one retry. Covers BOTH a validation-level rejection (report
    # present, not approved) and a grounding-level drop (no report at all,
    # e.g. an unsupported chart type dropped before there was anything to
    # merge/validate).
    if repair_hint is not None and (report is None or report.status != "approved"):
        logger.info("ask_to_visualize delta rejected; issuing one repair retry")
        repair_user = append_repair_constraints(user, repair_hint)
        raw2, failure2, attempt2 = _run_delta_llm_loop(system, repair_user, broker, tier, complete_json_fn)
        attempt += attempt2
        if failure2 is None:
            items2 = _ground(raw2)
            if not isinstance(items2, DeltaDraftResult):
                report2, _hint2 = _validate(items2, 2)
                items, report = items2, report2

    if items.new_visualization is None:
        return DeltaDraftResult(status="invalid", items=items, preview_text=_preview_text(items, existing_spec),
                                would_validate=False, attempts=attempt)

    would_validate = report is not None and report.status == "approved"
    return DeltaDraftResult(
        status="valid" if would_validate else "invalid", items=items,
        preview_text=_preview_text(items, existing_spec), would_validate=would_validate,
        validation_errors=[f"{e.code}: {e.reference}" for e in report.errors] if report else [],
        attempts=attempt,
    )


def confirm_delta(
    dsn: str, workspace_id: int, dataset_id: str,
    new_kpi: Any = None, new_analysis: Any = None, new_visualization: Any = None,
) -> PlannerResult:
    """Re-merge and RE-VALIDATE (never trust the client-echoed draft), then
    persist and chain C10->C11->C12->C13->C14 exactly like `run_planner`
    does for a full spec — the chart appears in one call.
    """
    spec_store = DashboardSpecStore(dsn, workspace_id)
    try:
        latest = spec_store.latest(dataset_id)
    finally:
        spec_store.close()
    if latest is None or latest.spec is None:
        return PlannerResult(status="controlled_error", error_code="no_approved_spec",
                             error_message=f"no approved spec to extend for {dataset_id!r}")
    existing_spec = latest.spec

    cstore = ContextStore(dsn, workspace_id)
    try:
        ctx = cstore.latest(dataset_id)
    finally:
        cstore.close()
    if ctx is None:
        return PlannerResult(status="controlled_error", error_code="no_planning_context",
                             error_message=f"no planning context for {dataset_id!r}")

    items = DeltaSpecItems(new_kpi=new_kpi, new_analysis=new_analysis, new_visualization=new_visualization)
    items = _dedupe_delta_items(items, existing_spec)
    merged_spec = _merge_spec(existing_spec, items)
    val_ctx = _validation_context(ctx)
    report, _repair = validate_spec(merged_spec, val_ctx, validation_id=f"delta_confirm_{merged_spec.spec_id}",
                                     attempt=1)
    if report.status != "approved":
        return PlannerResult(status="controlled_failure", error_code="delta_validation_rejected",
                             spec=merged_spec, validation=report.model_dump(mode="json"))

    result = PlannerResult(status="valid", spec=merged_spec, validation=report.model_dump(mode="json"))
    spec_store = DashboardSpecStore(dsn, workspace_id)
    try:
        spec_store.save(result, dataset_id, existing_spec.dataset_version)
    finally:
        spec_store.close()

    _run_c10_for_approved(dsn, workspace_id, result)
    run_analysis_execution(dsn, workspace_id, dataset_id)
    compose_dashboard(dsn, workspace_id, dataset_id)

    logger.info("ask_to_visualize confirm ws=%s dataset=%s status=%s", workspace_id, dataset_id, result.status)
    return result
