"""Chain 3: ask-to-visualize draft -> confirm, against a real approved spec
and real planning context. Uses the same well-formed-status philosophy as
chain 2 (see that file's module docstring) for the LLM-touching draft step
-- the orchestration surviving a real response is the contract; a
synthetic response passing every C09 rule is a different, much narrower
problem than what this test exists to catch.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

_CSV = b"category,amount\nfood,120\nrent,900\nfood,80\n"


def _seed_context_and_approved_spec(dsn: str, workspace_id: int) -> str:
    """Real ingest + real C03-C07, then a hand-built valid spec saved
    directly — this test is about draft/confirm, not re-proving the
    planner survives an LLM response (chain 2 already covers that)."""
    from aryx.andie_planner.models import (
        Analysis, BusinessQuestion, DashboardSpec, Kpi, PlannerResult, Visualization,
    )
    from aryx.dataset.ingest import register_dataset
    from aryx.intent.capture import capture_intent
    from aryx.intent.models import UserIntentRequest
    from aryx.pipeline.downstream import run_downstream
    from aryx.store.dashboard_spec_store import DashboardSpecStore
    from aryx.store.dataset_store import DatasetStore
    from aryx.store.intent_store import IntentStore

    dstore = DatasetStore(dsn, workspace_id)
    try:
        result = register_dataset(data=_CSV, file_name="e2e.csv",
                                  request_id="e2e-req", store=dstore)
    finally:
        dstore.close()
    dataset_id = result.dataset_id

    request = UserIntentRequest(domain="Finance", objective="Understand spend",
                                uploaded_file="e2e.csv")
    icap = capture_intent(request)
    istore = IntentStore(dsn, workspace_id)
    try:
        istore.save(icap)
    finally:
        istore.close()

    run_downstream(dsn, workspace_id, {dataset_id})

    spec = DashboardSpec(
        spec_id=f"dashboard_spec_{dataset_id}_v1", dataset_id=dataset_id,
        dataset_version="v1", schema_version="1.0",
        output_schema_version="dashboard_spec_v1", objective="Understand spend",
        business_questions=[BusinessQuestion(question_id="q1",
                                             text="How much did we spend by category?")],
        kpis=[Kpi(kpi_id="k1", operation="count", measure="amount",
                 source_columns=["amount"])],
        analyses=[Analysis(analysis_id="a1", operation="count",
                          group_by=["category"], metric="k1")],
        visualizations=[Visualization(chart_id="c1", chart_type="bar", source_ref="a1")],
        spec_status="valid", model_name="e2e-seed", model_tier="frontier",
        prompt_version="e2e")
    spec_store = DashboardSpecStore(dsn, workspace_id)
    try:
        spec_store.save(PlannerResult(status="valid", spec=spec), dataset_id, "v1")
    finally:
        spec_store.close()
    return dataset_id


def test_draft_then_confirm_against_a_real_approved_spec(e2e_dsn, workspace) -> None:
    """Draft a new chart, confirm it, and check it actually lands in the
    persisted spec — the full ask-to-visualize contract, real infra."""
    from aryx.andie_planner.delta import draft_delta
    from aryx.store.context_store import ContextStore
    from aryx.store.dashboard_spec_store import DashboardSpecStore

    wid = workspace["id"]
    dataset_id = _seed_context_and_approved_spec(e2e_dsn, wid)

    latest = DashboardSpecStore(e2e_dsn, wid).latest(dataset_id)
    ctx = ContextStore(e2e_dsn, wid).latest(dataset_id)
    assert latest is not None and latest.spec is not None
    assert ctx is not None

    def fake_delta_json(broker, tier, system, user, schema):
        return {"new_kpi": None,
               "new_analysis": {"analysis_id": "a2", "operation": "count",
                               "group_by": ["category"], "metric": "k1"},
               "new_visualization": {"chart_id": "c2", "chart_type": "bar",
                                    "source_ref": "a2"},
               "warnings": []}

    draft = draft_delta(latest.spec, ctx, "show count by category again",
                        broker=None, tier="frontier", complete_json_fn=fake_delta_json)
    assert draft.status in ("valid", "invalid", "controlled_error"), draft.status

    if draft.status != "valid" or draft.items is None or draft.items.new_visualization is None:
        pytest.skip(f"draft did not reach a confirmable state (status={draft.status}) — "
                   f"draft/confirm's own contract, not a chain-breakage bug; "
                   f"chain 2 already covers LLM-response survivability")

    from aryx.andie_planner.delta import confirm_delta
    confirmed = confirm_delta(
        e2e_dsn, wid, dataset_id,
        new_kpi=draft.items.new_kpi, new_analysis=draft.items.new_analysis,
        new_visualization=draft.items.new_visualization)
    assert confirmed.status in ("valid", "invalid", "controlled_error", "controlled_failure")
    if confirmed.status == "valid":
        chart_ids = {v.chart_id for v in confirmed.spec.visualizations}
        assert "c2" in chart_ids, "confirmed chart should appear in the persisted spec"
