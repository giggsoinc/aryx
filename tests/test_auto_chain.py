"""Tests for the zero-click pipeline sequencing engine
(aryx.pipeline.auto_chain) — pure, no live DB, no live LLM. Every stage
function it calls already has its own test suite (test_andie_planner.py,
test_analysis_execution.py); these tests only verify auto_chain's
sequencing and stop-on-blocker branching, using fakes for JobStore/
DatasetStore and monkeypatched stage functions.

Job creation/debounce and the trigger entry points that call
`run_auto_chain` (start_chain, run_chain_now, trigger_chain_from_brief) live
in aryx.pipeline.chain_jobs — see test_chain_jobs.py.
"""
from __future__ import annotations

from types import SimpleNamespace

from aryx.analysis_execution.models import ExecutionRun
from aryx.andie_planner.models import PlannerResult
from aryx.dashboard_composition.models import (
    CompositionIssue, DashboardComponent, DashboardModel, DashboardSection,
)
from aryx.pipeline import auto_chain

DSN = "postgresql://unused/test"
WS = 7


# ── fakes ──────────────────────────────────────────────────────────────────

class FakeJobStore:
    """In-memory stand-in for aryx.store.job_store.JobStore."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.jobs: dict[str, dict] = {}
        self.stage_calls: list[tuple] = []
        self.finish_calls: list[tuple] = []

    def create(self, job_id, system, dataset, workspace_id=1):
        self.jobs[job_id] = {"job_id": job_id, "source_system": system,
                             "source_dataset": dataset, "workspace_id": workspace_id,
                             "status": "queued"}

    def update_stage(self, job_id, stage, pct, detail):
        self.stage_calls.append((job_id, stage, pct, detail))
        self.jobs[job_id]["status"] = "running"

    def finish(self, job_id, run_id, status, error=None):
        self.finish_calls.append((job_id, run_id, status, error))
        self.jobs[job_id]["status"] = status

    def list_recent(self, workspace_id=1):
        return list(self.jobs.values())

    def close(self):
        pass


class FakeDatasetStore:
    def __init__(self, dsn: str, workspace_id: int, dataset_ids: list[str]) -> None:
        self._ids = dataset_ids

    def list_versions(self, limit):
        return [SimpleNamespace(dataset_id=d) for d in self._ids]

    def close(self):
        pass


def _approved_planner_result() -> PlannerResult:
    return PlannerResult(status="valid", validation={"status": "approved"})


def _rejected_planner_result() -> PlannerResult:
    return PlannerResult(status="controlled_failure",
                         error_code="planner_validation_retry_exhausted",
                         validation={"status": "rejected"})


def _no_context_planner_result() -> PlannerResult:
    return PlannerResult(status="controlled_error", error_code="no_planning_context")


def _execution_run(status="completed", eligible=True, errors=None) -> ExecutionRun:
    return ExecutionRun(
        execution_run_id="run_1", execution_plan_id="plan_1", spec_id="spec_1",
        dataset_id=f"workspace_{WS}", dataset_version="v1", status=status,
        errors=errors or [], validation={"status": "approved" if eligible else "flagged",
                                         "eligible_for_dashboard": eligible})


_ONE_SECTION = [DashboardSection(section_id="sec_1", title="Overview", components=[
    DashboardComponent(component_id="c1", type="kpi_card", source_ref="kpi_1", position=0)])]


def _dashboard_model(status="valid", issues=None, sections=_ONE_SECTION) -> DashboardModel:
    return DashboardModel(
        dashboard_model_id="dash_1", spec_id="spec_1", dataset_id=f"workspace_{WS}",
        dataset_version="v1", composition_status=status, issues=issues or [],
        sections=sections)


def _patch_stores(monkeypatch, dataset_ids: list[str]) -> FakeJobStore:
    job_store = FakeJobStore(DSN)
    monkeypatch.setattr(auto_chain, "JobStore", lambda dsn: job_store)
    monkeypatch.setattr(auto_chain, "DatasetStore",
                        lambda dsn, ws: FakeDatasetStore(dsn, ws, dataset_ids))
    return job_store


# ── run_auto_chain: sequencing + stop-on-blocker ────────────────────────────

def test_idle_when_no_datasets(monkeypatch) -> None:
    job_store = _patch_stores(monkeypatch, dataset_ids=[])
    job_store.create("job1", "auto_chain", f"workspace_{WS}", WS)

    auto_chain.run_auto_chain(DSN, WS, "job1")

    assert job_store.finish_calls == [("job1", None, "complete", None)]


def test_idle_when_no_planning_context(monkeypatch) -> None:
    job_store = _patch_stores(monkeypatch, dataset_ids=["d1"])
    job_store.create("job1", "auto_chain", f"workspace_{WS}", WS)
    monkeypatch.setattr(auto_chain, "run_downstream", lambda *a, **k: None)
    monkeypatch.setattr(auto_chain, "run_planner_workspace",
                        lambda *a, **k: _no_context_planner_result())

    auto_chain.run_auto_chain(DSN, WS, "job1")

    assert job_store.finish_calls == [("job1", None, "complete", None)]


def test_blocked_on_c09_rejection(monkeypatch) -> None:
    job_store = _patch_stores(monkeypatch, dataset_ids=["d1"])
    job_store.create("job1", "auto_chain", f"workspace_{WS}", WS)
    monkeypatch.setattr(auto_chain, "run_downstream", lambda *a, **k: None)
    monkeypatch.setattr(auto_chain, "run_planner_workspace",
                        lambda *a, **k: _rejected_planner_result())

    auto_chain.run_auto_chain(DSN, WS, "job1")

    job_id, run_id, status, error = job_store.finish_calls[0]
    assert (job_id, run_id, status) == ("job1", None, "blocked")
    assert "planner" in error


def test_proceeds_to_execution_when_spec_approved_then_blocks_on_execution_failed(
    monkeypatch,
) -> None:
    job_store = _patch_stores(monkeypatch, dataset_ids=["d1"])
    job_store.create("job1", "auto_chain", f"workspace_{WS}", WS)
    monkeypatch.setattr(auto_chain, "run_downstream", lambda *a, **k: None)
    monkeypatch.setattr(auto_chain, "run_planner_workspace",
                        lambda *a, **k: _approved_planner_result())
    monkeypatch.setattr(auto_chain, "run_analysis_execution",
                        lambda *a, **k: _execution_run(status="failed",
                                                        errors=["no compiled plan"]))

    auto_chain.run_auto_chain(DSN, WS, "job1")

    job_id, run_id, status, error = job_store.finish_calls[0]
    assert status == "blocked"
    assert "execution" in error and "no compiled plan" in error


def test_blocked_when_execution_results_ineligible_for_dashboard(monkeypatch) -> None:
    job_store = _patch_stores(monkeypatch, dataset_ids=["d1"])
    job_store.create("job1", "auto_chain", f"workspace_{WS}", WS)
    monkeypatch.setattr(auto_chain, "run_downstream", lambda *a, **k: None)
    monkeypatch.setattr(auto_chain, "run_planner_workspace",
                        lambda *a, **k: _approved_planner_result())
    monkeypatch.setattr(auto_chain, "run_analysis_execution",
                        lambda *a, **k: _execution_run(status="completed", eligible=False))

    auto_chain.run_auto_chain(DSN, WS, "job1")

    job_id, run_id, status, error = job_store.finish_calls[0]
    assert status == "blocked"
    assert "execution" in error


def test_completes_through_dashboard_when_eligible(monkeypatch) -> None:
    job_store = _patch_stores(monkeypatch, dataset_ids=["d1"])
    job_store.create("job1", "auto_chain", f"workspace_{WS}", WS)
    monkeypatch.setattr(auto_chain, "run_downstream", lambda *a, **k: None)
    monkeypatch.setattr(auto_chain, "run_planner_workspace",
                        lambda *a, **k: _approved_planner_result())
    monkeypatch.setattr(auto_chain, "run_analysis_execution",
                        lambda *a, **k: _execution_run(status="completed", eligible=True))
    monkeypatch.setattr(auto_chain, "compose_dashboard",
                        lambda *a, **k: _dashboard_model(status="valid"))

    auto_chain.run_auto_chain(DSN, WS, "job1")

    assert job_store.finish_calls == [("job1", None, "complete", None)]


def test_blocked_when_dashboard_has_no_sections(monkeypatch) -> None:
    # Every visualization got dropped (e.g. no_approved_spec/no_execution_run,
    # or every ref failed to bind) — nothing at all to show is a real blocker.
    job_store = _patch_stores(monkeypatch, dataset_ids=["d1"])
    job_store.create("job1", "auto_chain", f"workspace_{WS}", WS)
    monkeypatch.setattr(auto_chain, "run_downstream", lambda *a, **k: None)
    monkeypatch.setattr(auto_chain, "run_planner_workspace",
                        lambda *a, **k: _approved_planner_result())
    monkeypatch.setattr(auto_chain, "run_analysis_execution",
                        lambda *a, **k: _execution_run(status="completed", eligible=True))
    monkeypatch.setattr(
        auto_chain, "compose_dashboard",
        lambda *a, **k: _dashboard_model(
            status="invalid", issues=[CompositionIssue(code="no_execution_run")], sections=[]))

    auto_chain.run_auto_chain(DSN, WS, "job1")

    job_id, run_id, status, error = job_store.finish_calls[0]
    assert status == "blocked"
    assert "dashboard" in error and "no_execution_run" in error


def test_completes_when_some_components_dropped_but_sections_exist(monkeypatch) -> None:
    # compose_components._build_components drops (never wrongly renders) a
    # component with a chart_type_mismatch/missing_computed_result issue —
    # composition_status="invalid" there just means SOME things were
    # dropped, not that nothing is safe to show. A dashboard with real,
    # partial sections is a success, not a blocker.
    job_store = _patch_stores(monkeypatch, dataset_ids=["d1"])
    job_store.create("job1", "auto_chain", f"workspace_{WS}", WS)
    monkeypatch.setattr(auto_chain, "run_downstream", lambda *a, **k: None)
    monkeypatch.setattr(auto_chain, "run_planner_workspace",
                        lambda *a, **k: _approved_planner_result())
    monkeypatch.setattr(auto_chain, "run_analysis_execution",
                        lambda *a, **k: _execution_run(status="completed", eligible=True))
    monkeypatch.setattr(
        auto_chain, "compose_dashboard",
        lambda *a, **k: _dashboard_model(
            status="invalid", issues=[CompositionIssue(code="chart_type_mismatch")],
            sections=_ONE_SECTION))

    auto_chain.run_auto_chain(DSN, WS, "job1")

    assert job_store.finish_calls == [("job1", None, "complete", None)]


def test_unexpected_exception_marks_failed_not_blocked(monkeypatch) -> None:
    job_store = _patch_stores(monkeypatch, dataset_ids=["d1"])
    job_store.create("job1", "auto_chain", f"workspace_{WS}", WS)

    def _boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(auto_chain, "run_downstream", _boom)

    auto_chain.run_auto_chain(DSN, WS, "job1")

    job_id, run_id, status, error = job_store.finish_calls[0]
    assert status == "failed"
    assert "kaboom" in error
