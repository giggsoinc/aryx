"""Glue: compose the dashboard model for a workspace's approved, executed,
and post-execution-validated spec (C14). On-demand only, like C08/C12 —
triggered explicitly via POST /dashboard-model/run.
"""
from __future__ import annotations

import logging
import uuid

from aryx.andie_planner.models import DashboardSpec
from aryx.dashboard_composition.compose import DEFAULT_MAX_COLUMNS, compose, revalidate
from aryx.dashboard_composition.models import CompositionIssue, DashboardModel
from aryx.dashboard_composition.narrate import apply_titles, suggest_titles
from aryx.store.dashboard_model_store import DashboardModelStore
from aryx.store.dashboard_spec_store import DashboardSpecStore
from aryx.store.execution_run_store import ExecutionRunStore

logger = logging.getLogger(__name__)


def compose_dashboard(
    dsn: str, workspace_id: int, dataset_id: str, *,
    audience: str = "", maximum_columns: int = DEFAULT_MAX_COLUMNS,
    maximum_primary_charts: int | None = None,
    use_llm: bool = False, tier: str = "cheap", broker=None, complete_json_fn=None,
) -> DashboardModel:
    """Compose `dataset_id`'s (a real dataset_id in single-dataset mode,
    "workspace_{id}" in workspace mode) dashboard model. Always returns a
    typed DashboardModel; never raises.

    Gated on C13: composition refuses to run against a spec/run pair C13
    didn't mark `eligible_for_dashboard` — arranging unvalidated results is
    exactly the invented-content risk this whole pipeline exists to prevent.
    """
    dashboard_model_id = f"dashboard_{dataset_id}_{uuid.uuid4().hex[:8]}"

    spec_store = DashboardSpecStore(dsn, workspace_id)
    try:
        planner_result = spec_store.latest(dataset_id)
    finally:
        spec_store.close()
    spec = planner_result.spec if planner_result else None
    if spec is None:
        return DashboardModel(
            dashboard_model_id=dashboard_model_id, spec_id="", dataset_id=dataset_id,
            dataset_version="", audience=audience, composition_status="invalid",
            issues=[CompositionIssue(code="no_approved_spec")])

    run_store = ExecutionRunStore(dsn, workspace_id)
    try:
        run = run_store.latest(dataset_id)
    finally:
        run_store.close()
    if run is None:
        return DashboardModel(
            dashboard_model_id=dashboard_model_id, spec_id=spec.spec_id, dataset_id=dataset_id,
            dataset_version=spec.dataset_version, audience=audience, composition_status="invalid",
            issues=[CompositionIssue(code="no_execution_run")])

    validation = run.validation or {}
    if not validation.get("eligible_for_dashboard"):
        return DashboardModel(
            dashboard_model_id=dashboard_model_id, spec_id=spec.spec_id, dataset_id=dataset_id,
            dataset_version=spec.dataset_version, audience=audience, composition_status="invalid",
            issues=[CompositionIssue(code="results_not_eligible",
                                     detail=f"C13 status={validation.get('status', 'unknown')!r}")])

    max_charts_kwargs = {} if maximum_primary_charts is None else \
        {"maximum_primary_charts": maximum_primary_charts}
    sections, issues = compose(spec, run, **max_charts_kwargs)
    composed_by = "deterministic"
    dashboard_title = ""

    if use_llm and broker is not None and complete_json_fn is not None:
        suggestion = suggest_titles(sections, audience, spec.objective,
                                    broker=broker, complete_json_fn=complete_json_fn, tier=tier)
        if suggestion is not None:
            llm_title, section_titles = suggestion
            narrated_sections = apply_titles(sections, section_titles)
            post_llm_issues = revalidate(narrated_sections)
            if not post_llm_issues:
                sections = narrated_sections
                dashboard_title = llm_title
                composed_by = "llm_assisted"
            else:
                logger.warning("C14 discarding LLM titles — failed revalidation: %s", post_llm_issues)

    model = DashboardModel(
        dashboard_model_id=dashboard_model_id, spec_id=spec.spec_id, dataset_id=dataset_id,
        dataset_version=spec.dataset_version, title=dashboard_title or _default_title(spec),
        audience=audience, sections=sections, max_columns=maximum_columns,
        composition_status="invalid" if issues else "valid", issues=issues,
        composed_by=composed_by,
    )
    store = DashboardModelStore(dsn, workspace_id)
    try:
        store.save(model)
    finally:
        store.close()
    logger.info("dashboard_composition ws=%s dataset=%s status=%s sections=%d composed_by=%s",
               workspace_id, dataset_id, model.composition_status, len(sections), composed_by)
    return model


def _default_title(spec: DashboardSpec) -> str:
    return spec.objective.strip() or "Dashboard"
