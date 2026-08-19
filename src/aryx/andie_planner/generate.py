"""Planning orchestration (C08): prompt -> LLM -> ground -> typed result.

Mirrors the component Procedure:
  1/2. build the versioned prompt from approved resources only (prompt.py)
  3.   request schema-conforming JSON from the LLM (low temperature via the
       broker's pinned model spec; complete_json handles provider dispatch)
  4-7. (the LLM's job, re-verified in code, never trusted) map concepts to
       real columns, propose questions/KPIs, pick only catalogued
       operations/charts, include assumptions/warnings
  8.   parse WITHOUT EXECUTING any content — ground_spec never evaluates a
       formula or filter, it only validates structure and references
  9.   retry malformed JSON once, then return a typed controlled_error

The local Ollama path (format=json) guarantees syntactically valid JSON but
silently degrades unparseable output to `{}` rather than raising — so
"malformed" here means "missing the required top-level keys", not a parse
exception. A raised exception (timeout, connection failure) is the other
retry-then-fail path.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from aryx.andie_planner.filter_repair import repair_missing_filters
from aryx.andie_planner.ground import ground_spec
from aryx.andie_planner.models import PlannerResult
from aryx.andie_planner.prompt import (
    PROMPT_VERSION,
    append_repair_constraints,
    build_planner_prompt,
    build_workspace_planner_prompt,
    repair_prompt,
)
from aryx.andie_planner.schema import DASHBOARD_SPEC_SCHEMA

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2  # one real attempt + one retry, per the spec's "retry once"

CompleteJsonFn = Callable[[Any, str, str, str, dict], dict]


class PlanningContextLike(Protocol):
    """The subset of C07's PlanningContext this component depends on."""

    dataset_id: str
    dataset_version: str
    domain: str
    approved_columns: list[Any]
    approved_graph_paths: list[str]
    graph_path_hints: list[Any]
    graph_quality_notes: list[str]
    supported_operations: list[str]
    supported_charts: list[str]


def _is_malformed(raw: Any) -> bool:
    """True when the model returned nothing usable to ground."""
    if not isinstance(raw, dict):
        return True
    return not (raw.get("business_questions") or raw.get("kpis"))


def _model_name(broker: Any, tier: str) -> str:
    try:
        return broker.choose(tier).name
    except Exception:  # noqa: BLE001 — provenance only, never fatal
        return ""


def _run_llm_loop(
    system: str, user: str, broker: Any, tier: str, complete_json_fn: CompleteJsonFn,
) -> tuple[dict | None, PlannerResult | None, int]:
    """Retry-once-then-controlled-error state machine (step 9), shared by
    single-dataset and workspace-scope generation — the mechanics are
    identical, only the prompt/grounding differ per caller.

    Returns (raw, None, attempt) on success, or (None, controlled_error, attempt)
    once both attempts are exhausted. Never raises.
    """
    raw: dict = {}
    last_error = ""
    attempt = 0
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            raw = complete_json_fn(broker, tier, system, user, DASHBOARD_SPEC_SCHEMA)
        except Exception as exc:  # noqa: BLE001 — broker/provider failure
            last_error = str(exc)
            logger.warning("andie_planner llm call failed attempt=%d: %s", attempt, exc)
            if attempt >= _MAX_ATTEMPTS:
                return None, PlannerResult(status="controlled_error", error_code="llm_call_failed",
                                           error_message=last_error, attempts=attempt), attempt
            continue
        if _is_malformed(raw):
            last_error = "model returned no business_questions/kpis"
            logger.warning("andie_planner malformed response attempt=%d", attempt)
            if attempt >= _MAX_ATTEMPTS:
                return None, PlannerResult(status="controlled_error", error_code="malformed_json",
                                           error_message=last_error, attempts=attempt), attempt
            user = repair_prompt(user, last_error)
            continue
        return raw, None, attempt
    return None, PlannerResult(  # pragma: no cover — loop always returns/breaks above
        status="controlled_error", error_code="malformed_json",
        error_message=last_error, attempts=attempt), attempt


def assemble_spec(
    planning_context: PlanningContextLike,
    *,
    objective: str,
    brief_context: str = "",
    target_audience: str = "",
    output_schema_version: str = "dashboard_spec_v1",
    broker: Any,
    tier: str = "frontier",
    prompt_version: str = PROMPT_VERSION,
    complete_json_fn: CompleteJsonFn,
    repair_constraints: str = "",
    user_preferences: dict | None = None,
) -> PlannerResult:
    """Draft, ground, and return a candidate dashboard spec — never raises.

    Args:
        complete_json_fn: injected so tests can supply a fake LLM call
            without hitting a real model (signature matches aryx.llm.complete_json).
        repair_constraints: optional C09 (pre-execution validation) rejection
            constraints from a prior attempt, appended to the prompt for the
            one allowed correction retry. Empty by default — a no-op, so
            existing callers see identical behavior.
        user_preferences: C01 IntentPreferences hints (see prompt.py) — empty
            by default, a no-op.
    """
    approved_columns = [
        {"name": c.name, "type": c.type, "sample_values": c.sample_values}
        for c in planning_context.approved_columns
    ]
    system, user = build_planner_prompt(
        approved_columns=approved_columns,
        approved_graph_paths=list(planning_context.approved_graph_paths),
        supported_operations=list(planning_context.supported_operations),
        supported_charts=list(planning_context.supported_charts),
        objective=objective, target_audience=target_audience,
        output_schema_version=output_schema_version,
        domain=getattr(planning_context, "domain", ""),
        brief_context=brief_context,
        user_preferences=user_preferences,
        graph_path_hints=[{"path_id": h.path_id, "label": h.label, "depth": h.depth}
                          for h in getattr(planning_context, "graph_path_hints", []) or []],
        graph_quality_notes=list(getattr(planning_context, "graph_quality_notes", []) or []),
    )
    if repair_constraints:
        user = append_repair_constraints(user, repair_constraints)

    raw, failure, attempt = _run_llm_loop(system, user, broker, tier, complete_json_fn)
    if failure is not None:
        return failure

    # Step 8 — parse WITHOUT EXECUTING: ground_spec only validates references,
    # it never evaluates a filter/formula or runs the analysis. Wrapped
    # defensively: a local small model can emit a well-formed-but-wrong-typed
    # JSON value (e.g. a bool where a policy string was expected) that
    # ground.py's field coercion doesn't yet anticipate — that must still
    # become a controlled_error, never an unhandled exception to the caller.
    try:
        spec = ground_spec(
            raw, dataset_id=planning_context.dataset_id,
            dataset_version=planning_context.dataset_version,
            approved_columns=approved_columns,
            approved_operations=list(planning_context.supported_operations),
            approved_charts=list(planning_context.supported_charts),
            approved_graph_paths=list(planning_context.approved_graph_paths),
            objective=objective, target_audience=target_audience,
            output_schema_version=output_schema_version,
            model_name=_model_name(broker, tier), model_tier=tier,
            prompt_version=prompt_version,
        )
    except Exception as exc:  # noqa: BLE001 — grounding must never crash the caller
        logger.warning("andie_planner grounding failed: %s", exc, exc_info=True)
        return PlannerResult(status="controlled_error", error_code="grounding_failed",
                             error_message=str(exc), attempts=attempt)

    # Step 8a — targeted micro-repair: fix KPI filters the model left empty
    # with one narrow follow-up call, before C09 ever sees them. Best-effort
    # and purely additive — never invents, never raises, never changes
    # spec_status by itself (C09 still re-validates everything downstream).
    try:
        spec = repair_missing_filters(
            spec, objective=objective, approved_columns=approved_columns,
            broker=broker, tier=tier, complete_json_fn=complete_json_fn)
    except Exception:  # noqa: BLE001 — best-effort, never blocks the caller
        logger.warning("andie_planner filter micro-repair failed", exc_info=True)
    return PlannerResult(status=spec.spec_status, spec=spec, attempts=attempt)


class WorkspaceContextLike(Protocol):
    """The subset of a workspace-wide PlanningContext this component needs."""

    dataset_id: str
    dataset_version: str
    domain: str
    datasets: list[Any]
    approved_graph_paths: list[str]
    graph_path_hints: list[Any]
    graph_quality_notes: list[str]
    supported_operations: list[str]
    supported_charts: list[str]


def assemble_workspace_spec(
    workspace_context: WorkspaceContextLike,
    *,
    objective: str,
    brief_context: str = "",
    target_audience: str = "",
    output_schema_version: str = "dashboard_spec_v1",
    broker: Any,
    tier: str = "frontier",
    prompt_version: str = PROMPT_VERSION,
    complete_json_fn: CompleteJsonFn,
    repair_constraints: str = "",
    user_preferences: dict | None = None,
) -> PlannerResult:
    """Same as `assemble_spec`, but spans every dataset in the workspace.

    Every KPI/analysis in the result carries its own `dataset_id`; grounding
    checks each one against ONLY that dataset's real columns (see ground.py),
    since column names collide across unrelated datasets often enough that a
    flattened check would be ambiguous.

    Args:
        repair_constraints: see `assemble_spec` — empty by default, a no-op.
        user_preferences: see `assemble_spec` — empty by default, a no-op.
    """
    dataset_groups = [
        {"dataset_id": d.dataset_id,
         "approved_columns": [
             {"name": c.name, "type": c.type, "sample_values": c.sample_values}
             for c in d.approved_columns
         ]}
        for d in workspace_context.datasets
    ]
    system, user = build_workspace_planner_prompt(
        datasets=dataset_groups,
        approved_graph_paths=list(workspace_context.approved_graph_paths),
        supported_operations=list(workspace_context.supported_operations),
        supported_charts=list(workspace_context.supported_charts),
        objective=objective, target_audience=target_audience,
        output_schema_version=output_schema_version,
        domain=getattr(workspace_context, "domain", ""),
        brief_context=brief_context,
        user_preferences=user_preferences,
        graph_path_hints=[{"path_id": h.path_id, "label": h.label, "depth": h.depth}
                          for h in getattr(workspace_context, "graph_path_hints", []) or []],
        graph_quality_notes=list(getattr(workspace_context, "graph_quality_notes", []) or []),
    )
    if repair_constraints:
        user = append_repair_constraints(user, repair_constraints)

    raw, failure, attempt = _run_llm_loop(system, user, broker, tier, complete_json_fn)
    if failure is not None:
        return failure

    try:
        spec = ground_spec(
            raw, dataset_id=workspace_context.dataset_id,
            dataset_version=workspace_context.dataset_version,
            approved_columns=[],
            approved_operations=list(workspace_context.supported_operations),
            approved_charts=list(workspace_context.supported_charts),
            approved_graph_paths=list(workspace_context.approved_graph_paths),
            datasets=dataset_groups,
            objective=objective, target_audience=target_audience,
            output_schema_version=output_schema_version,
            model_name=_model_name(broker, tier), model_tier=tier,
            prompt_version=prompt_version,
        )
    except Exception as exc:  # noqa: BLE001 — grounding must never crash the caller
        logger.warning("andie_planner workspace grounding failed: %s", exc, exc_info=True)
        return PlannerResult(status="controlled_error", error_code="grounding_failed",
                             error_message=str(exc), attempts=attempt)

    try:
        spec = repair_missing_filters(
            spec, objective=objective,
            columns_by_dataset={d["dataset_id"]: d["approved_columns"] for d in dataset_groups},
            broker=broker, tier=tier, complete_json_fn=complete_json_fn)
    except Exception:  # noqa: BLE001 — best-effort, never blocks the caller
        logger.warning("andie_planner workspace filter micro-repair failed", exc_info=True)
    return PlannerResult(status=spec.spec_status, spec=spec, attempts=attempt)
