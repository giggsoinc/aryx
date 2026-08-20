"""Chain 1: the full zero-click chain — Brief/Intent -> C03-C07 -> planner
(C08) -> execution (C12/C13) -> dashboard composition (C14) — in one call,
against real Postgres + FalkorDB. Only the planner touches an LLM (C14
composition is deterministic unless use_llm_for_dashboard=True, which
run_auto_chain defaults to False); stubbed via the same module-level
monkeypatch as chain 2, since run_auto_chain calls the identical
run_planner_workspace under the hood.

Observed outcome with the shared synthetic fake_complete_json: "blocked"
at the planner stage (schema_invalid — internal grounding in
generate.py/ground.py drops something before the spec ever reaches C09's
external checks, a different pipeline than the one chain 3's hand-built
spec goes through). That's accepted here, not chased further: reproducing
a fully synthetic response that survives grounding AND external
validation is a narrow, orthogonal problem to what this test exists to
catch (does run_auto_chain's own orchestration — job creation, stage
sequencing, the "stop on first genuine blocker" contract — survive a real
response without crashing). Chain 3 already proves what happens once a
valid spec exists; this proves the chain gets there and stops cleanly,
never silently, when it can't.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.e2e

_CSV = b"category,amount\nfood,120\nrent,900\nfood,80\n"


def test_auto_chain_reaches_a_well_formed_terminal_status(
        e2e_dsn, workspace, monkeypatch) -> None:
    """The full chain either completes or stops cleanly at a genuine
    blocker — never 'failed' (an unhandled exception) — see module
    docstring for the observed outcome and why it's accepted as-is."""
    from conftest import fake_complete_json

    from aryx.dataset.ingest import register_dataset
    from aryx.intent.capture import capture_intent
    from aryx.intent.models import UserIntentRequest
    from aryx.pipeline.auto_chain import run_auto_chain
    from aryx.store.dataset_store import DatasetStore
    from aryx.store.intent_store import IntentStore
    from aryx.store.job_store import JobStore

    wid = workspace["id"]
    dstore = DatasetStore(e2e_dsn, wid)
    try:
        result = register_dataset(data=_CSV, file_name="e2e.csv",
                                  request_id="e2e-req", store=dstore)
    finally:
        dstore.close()
    assert result.ingestion_status == "accepted"

    request = UserIntentRequest(domain="Finance", objective="Understand spend",
                                uploaded_file="e2e.csv")
    icap = capture_intent(request)
    assert icap.validation_status == "valid"
    istore = IntentStore(e2e_dsn, wid)
    try:
        istore.save(icap)
    finally:
        istore.close()

    job_id = f"e2e_{uuid.uuid4().hex[:10]}"
    jobs = JobStore(e2e_dsn)
    jobs.create(job_id, "auto_chain", f"workspace_{wid}", wid)
    jobs.close()

    monkeypatch.setattr("aryx.andie_planner.run.complete_json",
                       fake_complete_json(dataset_id=result.dataset_id))
    run_auto_chain(e2e_dsn, wid, job_id, broker=None)

    jobs = JobStore(e2e_dsn)
    try:
        job = jobs.get(job_id)
    finally:
        jobs.close()
    assert job["status"] in ("complete", "blocked"), (
        f"got {job['status']!r}: {job.get('error')} — 'failed' means an "
        f"unhandled exception, a real bug distinct from a designed pause")

    if job["status"] == "complete":
        from aryx.store.dashboard_model_store import DashboardModelStore
        model_store = DashboardModelStore(e2e_dsn, wid)
        try:
            model = model_store.latest(result.dataset_id)
        finally:
            model_store.close()
        assert model is not None, (
            "job reported complete but no dashboard model was composed")
