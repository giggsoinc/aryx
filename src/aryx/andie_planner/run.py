"""Glue: run C08 on-demand for a dataset and persist the result.

Loads the latest C07 planning context, resolves the objective/audience from
the dataset's C01 intent when not given explicitly, calls the LLM (reason
tier), grounds it (C08's ground.py), then runs it through C09 (pre-execution
specification validation) with exactly one bounded repair retry before
persisting the PlannerResult — valid, invalid, controlled_error, or (once C09
rejects both the original and its one retry) controlled_failure.
"""
from __future__ import annotations

import logging
import uuid

from aryx.andie_planner.generate import assemble_spec, assemble_workspace_spec
from aryx.andie_planner.models import DashboardSpec, PlannerResult
from aryx.llm import complete_json
from aryx.preprocess.run import run_preprocess
from aryx.spec_validation.checks import ValidationContext
from aryx.spec_validation.run import run_spec_validation
from aryx.spec_validation.validate import repair_constraints_text
from aryx.store.context_store import ContextStore
from aryx.store.dashboard_spec_store import DashboardSpecStore
from aryx.store.dataset_store import DatasetStore
from aryx.store.profile_store import ProfileStore

logger = logging.getLogger(__name__)


def _resolve_intent(dsn: str, workspace_id: int, dataset_id: str) -> tuple[str, str]:
    """Best-effort (objective, target_audience) from the dataset's C01 intent."""
    try:
        dstore = DatasetStore(dsn, workspace_id)
        try:
            latest_ds = dstore.latest(dataset_id)
        finally:
            dstore.close()
        if not latest_ds or not latest_ds.request_id:
            return "", ""
        from aryx.store.intent_store import IntentStore
        istore = IntentStore(dsn, workspace_id)
        try:
            intent = istore.get(latest_ds.request_id)
        finally:
            istore.close()
        if not intent:
            return "", ""
        return intent.objective, intent.preferences.target_audience
    except Exception:  # noqa: BLE001 — objective/audience are hints only
        return "", ""


def _single_dataset_ctx(planning_context) -> ValidationContext:
    return ValidationContext(
        approved_columns={c.name: c.type for c in planning_context.approved_columns},
        approved_graph_paths=frozenset(planning_context.approved_graph_paths),
        approved_operations=frozenset(planning_context.supported_operations),
        approved_charts=frozenset(planning_context.supported_charts),
    )


def _workspace_ctx(workspace_context) -> ValidationContext:
    return ValidationContext(
        columns_by_dataset={
            d.dataset_id: {c.name: c.type for c in d.approved_columns}
            for d in workspace_context.datasets
        },
        approved_graph_paths=frozenset(workspace_context.approved_graph_paths),
        approved_operations=frozenset(workspace_context.supported_operations),
        approved_charts=frozenset(workspace_context.supported_charts),
    )


def _run_c09_with_bounded_retry(
    dsn: str, workspace_id: int, result: PlannerResult, val_ctx: ValidationContext,
    *, retry_generate,
) -> PlannerResult:
    """Validate `result.spec` via C09; on rejection, ask `retry_generate` (a
    zero-arg callable closing over the LLM/prompt context) for exactly ONE
    corrected candidate, then validate that. Never more than one retry —
    enforced both here and server-side in run_spec_validation's attempt cap.

    Returns the final PlannerResult with `.validation` attached — either the
    original result (approved), a fresh result from the retry (approved), or
    a terminal `controlled_failure` PlannerResult once both are rejected.
    """
    if result.spec is None:
        return result  # malformed/llm_call_failed — C09 never runs on no spec

    validation_id = f"validation_{result.spec.spec_id}_{uuid.uuid4().hex[:8]}"
    report, repair = run_spec_validation(dsn, workspace_id, validation_id, result.spec, val_ctx)
    result.validation = report.model_dump(mode="json")
    if report.status == "approved":
        return result
    if repair is None:
        # No retry allowed (shouldn't happen on a first attempt, but the cap
        # is authoritative) — terminal failure on the original candidate.
        return PlannerResult(
            status="controlled_failure", error_code="planner_validation_retry_exhausted",
            spec=result.spec, attempts=result.attempts, validation=result.validation,
        )

    logger.info("C09 rejected spec=%s ws=%s; issuing one repair retry",
                result.spec.spec_id, workspace_id)
    retry_result: PlannerResult = retry_generate(repair_constraints_text(repair))
    if retry_result.spec is None:
        return retry_result  # LLM-level failure on the retry — already a controlled_error

    report2, _ = run_spec_validation(dsn, workspace_id, validation_id, retry_result.spec, val_ctx)
    retry_result.validation = report2.model_dump(mode="json")
    if report2.status == "approved":
        retry_result.attempts += result.attempts
        return retry_result
    return PlannerResult(
        status="controlled_failure", error_code="planner_validation_retry_exhausted",
        spec=retry_result.spec, attempts=result.attempts + retry_result.attempts,
        validation=retry_result.validation,
    )


def _run_c10_for_approved(dsn: str, workspace_id: int, result: PlannerResult) -> None:
    """Chain C10 onto an approved spec — one AnalysisDataset per dataset the
    spec's KPIs/analyses actually reference. Mutates `result.analysis_datasets`
    in place; best-effort, never blocks or downgrades the C08/C09 outcome."""
    if result.spec is None or not result.validation or result.validation.get("status") != "approved":
        return
    spec: DashboardSpec = result.spec
    dataset_ids = sorted({k.dataset_id for k in spec.kpis if k.dataset_id} |
                         {a.dataset_id for a in spec.analyses if a.dataset_id})
    for did in dataset_ids:
        pstore = ProfileStore(dsn, workspace_id)
        try:
            profile = pstore.latest(did)
        finally:
            pstore.close()
        if profile is None:
            continue
        try:
            analysis_dataset = run_preprocess(dsn, workspace_id, did, spec, profile)
        except Exception:  # noqa: BLE001 — C10 is additive, never blocks the spec result
            logger.warning("C10 preprocess failed ws=%s dataset=%s", workspace_id, did, exc_info=True)
            continue
        if analysis_dataset is not None:
            result.analysis_datasets.append(analysis_dataset.model_dump(mode="json"))


def run_planner(dsn: str, workspace_id: int, dataset_id: str, *,
                objective: str | None = None, target_audience: str | None = None,
                tier: str = "frontier", broker=None) -> PlannerResult:
    """Assemble and persist a dashboard spec for a dataset's planning context."""
    cstore = ContextStore(dsn, workspace_id)
    try:
        ctx = cstore.latest(dataset_id)
    finally:
        cstore.close()
    if ctx is None:
        return PlannerResult(status="controlled_error", error_code="no_planning_context",
                             error_message=f"no planning context for dataset {dataset_id!r}")

    resolved_obj, resolved_aud = ("", "")
    if objective is None or target_audience is None:
        resolved_obj, resolved_aud = _resolve_intent(dsn, workspace_id, dataset_id)

    if broker is None:
        from aryx.api.admin_api import _local_broker
        broker = _local_broker()

    final_objective = objective if objective is not None else (resolved_obj or ctx.objective)
    final_audience = target_audience if target_audience is not None else resolved_aud

    result = assemble_spec(
        ctx, objective=final_objective, target_audience=final_audience,
        broker=broker, tier=tier, complete_json_fn=complete_json,
    )

    def _retry(constraints: str) -> PlannerResult:
        return assemble_spec(
            ctx, objective=final_objective, target_audience=final_audience,
            broker=broker, tier=tier, complete_json_fn=complete_json,
            repair_constraints=constraints,
        )

    result = _run_c09_with_bounded_retry(
        dsn, workspace_id, result, _single_dataset_ctx(ctx), retry_generate=_retry)
    _run_c10_for_approved(dsn, workspace_id, result)

    store = DashboardSpecStore(dsn, workspace_id)
    try:
        store.save(result, dataset_id, ctx.dataset_version)
    finally:
        store.close()
    logger.info("andie_planner ws=%s dataset=%s status=%s", workspace_id, dataset_id, result.status)
    return result


def _resolve_workspace_intent(dsn: str, workspace_id: int) -> tuple[str, str]:
    """Best-effort (objective, target_audience) from the workspace's most
    recent C01 intent — not tied to any single dataset."""
    try:
        from aryx.store.intent_store import IntentStore
        istore = IntentStore(dsn, workspace_id)
        try:
            recent = istore.list(1)
        finally:
            istore.close()
        if not recent:
            return "", ""
        return recent[0].objective, recent[0].preferences.target_audience
    except Exception:  # noqa: BLE001 — objective/audience are hints only
        return "", ""


def run_planner_workspace(dsn: str, workspace_id: int, *,
                          objective: str | None = None, target_audience: str | None = None,
                          tier: str = "frontier", broker=None) -> PlannerResult:
    """Assemble and persist a dashboard spec spanning the WHOLE workspace.

    Uses the workspace-wide planning context (C07's merged, per-dataset
    grouped context) instead of a single dataset's — every KPI/analysis in
    the result declares which dataset it came from (see ground.py).
    """
    cstore = ContextStore(dsn, workspace_id)
    try:
        ctx = cstore.latest(f"workspace_{workspace_id}")
    finally:
        cstore.close()
    if ctx is None:
        return PlannerResult(
            status="controlled_error", error_code="no_planning_context",
            error_message=f"no workspace-wide planning context for workspace {workspace_id}")

    resolved_obj, resolved_aud = ("", "")
    if objective is None or target_audience is None:
        resolved_obj, resolved_aud = _resolve_workspace_intent(dsn, workspace_id)

    if broker is None:
        from aryx.api.admin_api import _local_broker
        broker = _local_broker()

    final_objective = objective if objective is not None else (resolved_obj or ctx.objective)
    final_audience = target_audience if target_audience is not None else resolved_aud

    result = assemble_workspace_spec(
        ctx, objective=final_objective, target_audience=final_audience,
        broker=broker, tier=tier, complete_json_fn=complete_json,
    )

    def _retry(constraints: str) -> PlannerResult:
        return assemble_workspace_spec(
            ctx, objective=final_objective, target_audience=final_audience,
            broker=broker, tier=tier, complete_json_fn=complete_json,
            repair_constraints=constraints,
        )

    result = _run_c09_with_bounded_retry(
        dsn, workspace_id, result, _workspace_ctx(ctx), retry_generate=_retry)
    _run_c10_for_approved(dsn, workspace_id, result)

    store = DashboardSpecStore(dsn, workspace_id)
    try:
        store.save(result, f"workspace_{workspace_id}", ctx.dataset_version)
    finally:
        store.close()
    logger.info("andie_planner workspace ws=%s status=%s", workspace_id, result.status)
    return result
