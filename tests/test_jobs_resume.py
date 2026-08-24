"""Regression: resuming a crashed run must re-apply skip_resolution.

Found via raven-review of the DEC-011 transactional bypass: `skip_resolution`
was a plain run_pipeline() argument, never persisted anywhere. Resuming a
crashed transactional-type (e.g. Order) ingest via POST /admin/jobs/{id}/resume
silently defaulted back to False and ran full entity resolution — reintroducing
the exact false-merge bug DEC-011 exists to prevent. Fixed by folding
skip_resolution into the same checkpoint `detail` dict that already carries
ontology_type/match_keys across a resume (orchestrate.py), and reading it back
in _resume_meta/_do_resume.
"""
from __future__ import annotations

from aryx.api import jobs_api


class _FakeTracker:
    """StageTracker stand-in: returns one checkpoint row with a fixed detail."""

    def __init__(self, dsn: str) -> None:
        pass

    def rows(self, run_id: int) -> list[dict]:
        return [{
            "stage": "discover", "status": "done",
            "detail": {
                "ontology_type": "Order", "match_keys": ["order_id"],
                "workspace_id": 1, "system": "file", "dataset": "orders.csv",
                "skip_resolution": True,
            },
        }]


class _FakeJobStore:
    def __init__(self, dsn: str) -> None:
        pass

    def update_stage(self, *args, **kwargs) -> None:
        pass

    def attach_run(self, *args, **kwargs) -> None:
        pass

    def heartbeat(self, *args, **kwargs) -> None:
        pass

    def finish(self, *args, **kwargs) -> None:
        pass

    def close(self) -> None:
        pass


def test_resume_meta_carries_skip_resolution_forward(monkeypatch) -> None:
    """_resume_meta must surface the persisted flag, not drop it."""
    monkeypatch.setattr("aryx.store.checkpoint_store.StageTracker", _FakeTracker)

    meta = jobs_api._resume_meta(999)

    assert meta["skip_resolution"] is True


def test_do_resume_passes_persisted_skip_resolution_into_run_pipeline(monkeypatch) -> None:
    """The actual regression: a crashed Order-ingest run resumed with
    skip_resolution=True in its checkpoint must call run_pipeline with
    skip_resolution=True, not silently fall back to full ER."""
    captured: dict = {}

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        return {"run_id": 999, "entities": 0, "relationships": 0}

    monkeypatch.setattr(jobs_api, "JobStore", _FakeJobStore)
    monkeypatch.setattr("aryx.api.admin_api._local_broker", lambda: object())
    monkeypatch.setattr("aryx.pipeline.orchestrate.run_pipeline", fake_run_pipeline)

    meta = {
        "ontology_type": "Order", "match_keys": ["order_id"],
        "system": "file", "dataset": "orders.csv", "skip_resolution": True,
    }
    jobs_api._do_resume("old-job", "new-job", 999, workspace_id=1, meta=meta)

    assert captured.get("skip_resolution") is True
    assert captured.get("resume_run_id") == 999


def test_do_resume_defaults_skip_resolution_false_when_absent(monkeypatch) -> None:
    """Old checkpoints written before this fix have no skip_resolution key —
    must default to False (original behaviour), not raise."""
    captured: dict = {}

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        return {"run_id": 999, "entities": 0, "relationships": 0}

    monkeypatch.setattr(jobs_api, "JobStore", _FakeJobStore)
    monkeypatch.setattr("aryx.api.admin_api._local_broker", lambda: object())
    monkeypatch.setattr("aryx.pipeline.orchestrate.run_pipeline", fake_run_pipeline)

    meta = {"ontology_type": "Company", "match_keys": ["name"],
            "system": "file", "dataset": "companies.csv"}
    jobs_api._do_resume("old-job", "new-job", 999, workspace_id=1, meta=meta)

    assert captured.get("skip_resolution") is False
