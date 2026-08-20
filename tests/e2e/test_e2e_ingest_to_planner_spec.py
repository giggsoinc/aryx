"""Chain 2: dataset ingest -> profile -> semantic -> graph intake/profile ->
planning context -> planner spec (C02-C08). C03-C07 are deterministic (no
LLM anywhere in that path — confirmed by reading every module involved), so
they run for real, unstubbed. Only C08 (the planner itself) touches an LLM,
stubbed here via aryx.andie_planner.run's module-level complete_json import.

Scope note: the fake LLM response's job is to prove the ORCHESTRATION
survives a real response coming back (grounding runs, C09 validates against
real profiled columns, a PlannerResult of some well-formed status returns)
-- not to guarantee "valid". Chasing a synthetic response through every C09
rule to force "valid" every time would test the fake response's shape, not
the chain. A well-formed non-crash outcome is the real contract here (see
PlannerResult/DeltaDraftResult's own docstrings elsewhere in this codebase
for the same philosophy).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

_CSV = b"category,amount\nfood,120\nrent,900\nfood,80\n"


def _seed_dataset(dsn: str, workspace_id: int) -> str:
    from aryx.dataset.ingest import register_dataset
    from aryx.store.dataset_store import DatasetStore
    store = DatasetStore(dsn, workspace_id)
    try:
        result = register_dataset(data=_CSV, file_name="e2e.csv",
                                  request_id="e2e-req", store=store)
    finally:
        store.close()
    assert result.ingestion_status == "accepted", result.errors
    return result.dataset_id


def _capture_intent(dsn: str, workspace_id: int, uploaded_file: str) -> None:
    from aryx.intent.capture import capture_intent
    from aryx.intent.models import UserIntentRequest
    from aryx.store.intent_store import IntentStore
    request = UserIntentRequest(
        domain="Finance", objective="Understand spend by category",
        uploaded_file=uploaded_file)
    result = capture_intent(request)
    assert result.validation_status == "valid", result.errors
    store = IntentStore(dsn, workspace_id)
    try:
        store.save(result)
    finally:
        store.close()


def test_ingest_through_downstream_produces_real_context(e2e_dsn, workspace) -> None:
    """C02-C07: no LLM, must all run and leave real rows behind."""
    from aryx.pipeline.downstream import run_downstream
    from aryx.store.context_store import ContextStore
    from aryx.store.profile_store import ProfileStore
    wid = workspace["id"]
    dataset_id = _seed_dataset(e2e_dsn, wid)
    _capture_intent(e2e_dsn, wid, uploaded_file="e2e.csv")

    run_downstream(e2e_dsn, wid, {dataset_id})

    profile_store = ProfileStore(e2e_dsn, wid)
    try:
        profile = profile_store.latest(dataset_id)
    finally:
        profile_store.close()
    assert profile is not None, "C03 should have profiled the dataset"

    ctx_store = ContextStore(e2e_dsn, wid)
    try:
        ctx = ctx_store.latest(dataset_id)
    finally:
        ctx_store.close()
    assert ctx is not None, "C07 should have assembled planning context"


def test_planner_produces_a_well_formed_result_from_real_context(
        e2e_dsn, workspace, monkeypatch) -> None:
    """C08 against real context, LLM stubbed — see module docstring for
    why any well-formed status counts, not just 'valid'."""
    from conftest import fake_complete_json

    from aryx.andie_planner.run import run_planner_workspace
    wid = workspace["id"]
    dataset_id = _seed_dataset(e2e_dsn, wid)
    _capture_intent(e2e_dsn, wid, uploaded_file="e2e.csv")

    from aryx.pipeline.downstream import run_downstream
    run_downstream(e2e_dsn, wid, {dataset_id})

    monkeypatch.setattr("aryx.andie_planner.run.complete_json",
                       fake_complete_json(dataset_id=dataset_id))
    result = run_planner_workspace(e2e_dsn, wid)

    # controlled_failure = C09 retry exhausted; controlled_error = malformed
    # model response; invalid = validated but rejected; valid = accepted.
    # All four are well-formed, typed outcomes — never a raw exception.
    assert result.status in ("valid", "invalid", "controlled_error",
                             "controlled_failure"), (
        f"unexpected status {result.status!r} — the chain should never "
        f"crash, only return a typed outcome")
