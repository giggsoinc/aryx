"""Tests for job bookkeeping and trigger entry points
(aryx.pipeline.chain_jobs) and the Brief -> Intent adapter
(aryx.intent.from_brief) — pure, no live DB, no live LLM.

run_auto_chain's own sequencing/stop-on-blocker branching is tested in
test_auto_chain.py; these tests only verify chain_jobs' debounce (reuse an
active job instead of enqueueing a duplicate) and how the three trigger
entry points wire up to it.
"""
from __future__ import annotations

from aryx.intent.capture import capture_intent
from aryx.intent.from_brief import brief_to_intent_request
from aryx.pipeline import chain_jobs

DSN = "postgresql://unused/test"
WS = 7


class FakeJobStore:
    """In-memory stand-in for aryx.store.job_store.JobStore."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.jobs: dict[str, dict] = {}
        self.finish_calls: list[tuple] = []

    def create(self, job_id, system, dataset, workspace_id=1):
        self.jobs[job_id] = {"job_id": job_id, "source_system": system,
                             "source_dataset": dataset, "workspace_id": workspace_id,
                             "status": "queued"}

    def finish(self, job_id, run_id, status, error=None):
        self.finish_calls.append((job_id, run_id, status, error))
        self.jobs[job_id]["status"] = status

    def list_recent(self, workspace_id=1):
        return list(self.jobs.values())

    def close(self):
        pass


class FakeIntentStore:
    def __init__(self, dsn: str, workspace_id: int) -> None:
        self.saved = []

    def save(self, intent):
        self.saved.append(intent)

    def close(self):
        pass


class FakeBackgroundTasks:
    def __init__(self) -> None:
        self.tasks: list[tuple] = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


class FakeSettings:
    def __init__(self, auto_chain_enabled: bool) -> None:
        self.auto_chain_enabled = auto_chain_enabled


def _patch_job_store(monkeypatch, *, auto_chain_enabled: bool = True) -> FakeJobStore:
    job_store = FakeJobStore(DSN)
    monkeypatch.setattr(chain_jobs, "JobStore", lambda dsn: job_store)
    monkeypatch.setattr(chain_jobs, "get_settings", lambda: FakeSettings(auto_chain_enabled))
    return job_store


# ── debounce: reuse an active job instead of enqueueing a duplicate ────────

def test_start_chain_reuses_active_job_instead_of_enqueueing_duplicate(monkeypatch) -> None:
    job_store = _patch_job_store(monkeypatch)
    job_store.create("existing_job", "auto_chain", f"workspace_{WS}", WS)
    job_store.jobs["existing_job"]["status"] = "running"
    bg = FakeBackgroundTasks()

    job_id = chain_jobs.start_chain(DSN, WS, bg)

    assert job_id == "existing_job"
    assert bg.tasks == []


def test_start_chain_enqueues_when_no_active_job(monkeypatch) -> None:
    _patch_job_store(monkeypatch)
    bg = FakeBackgroundTasks()

    job_id = chain_jobs.start_chain(DSN, WS, bg)

    assert len(bg.tasks) == 1
    fn, args, kwargs = bg.tasks[0]
    assert fn is chain_jobs.run_auto_chain
    assert args == (DSN, WS, job_id)


def test_run_chain_now_reuses_active_job_and_does_not_rerun(monkeypatch) -> None:
    job_store = _patch_job_store(monkeypatch)
    job_store.create("existing_job", "auto_chain", f"workspace_{WS}", WS)
    job_store.jobs["existing_job"]["status"] = "running"
    calls = []
    monkeypatch.setattr(chain_jobs, "run_auto_chain", lambda *a, **k: calls.append(a))

    job_id = chain_jobs.run_chain_now(DSN, WS)

    assert job_id == "existing_job"
    assert calls == []


# ── ARYX_AUTO_CHAIN_ENABLED gate (off by default — no LLM spend without it) ─

def test_start_chain_blocked_when_disabled(monkeypatch) -> None:
    job_store = _patch_job_store(monkeypatch, auto_chain_enabled=False)
    bg = FakeBackgroundTasks()

    job_id = chain_jobs.start_chain(DSN, WS, bg)

    assert bg.tasks == []  # never reaches run_auto_chain — no LLM call, no execution
    job_id, run_id, status, error = job_store.finish_calls[0]
    assert status == "blocked"
    assert "disabled" in error and "ARYX_AUTO_CHAIN_ENABLED" in error


def test_run_chain_now_blocked_when_disabled(monkeypatch) -> None:
    job_store = _patch_job_store(monkeypatch, auto_chain_enabled=False)
    calls = []
    monkeypatch.setattr(chain_jobs, "run_auto_chain", lambda *a, **k: calls.append(a))

    job_id = chain_jobs.run_chain_now(DSN, WS)

    assert calls == []
    job_id, run_id, status, error = job_store.finish_calls[0]
    assert status == "blocked"
    assert "disabled" in error


def test_trigger_chain_from_brief_blocked_when_disabled(monkeypatch) -> None:
    job_store = _patch_job_store(monkeypatch, auto_chain_enabled=False)
    intent_store = FakeIntentStore(DSN, WS)
    monkeypatch.setattr(chain_jobs, "IntentStore", lambda dsn, ws: intent_store)
    bg = FakeBackgroundTasks()

    job_id = chain_jobs.trigger_chain_from_brief(
        DSN, WS, {"domain": "sales", "aim": "understand renewals"}, bg)

    # A valid intent is still captured/persisted (cheap, no LLM) — only the
    # expensive chain itself is gated.
    assert intent_store.saved and intent_store.saved[0].validation_status == "valid"
    assert bg.tasks == []
    job_id, run_id, status, error = job_store.finish_calls[0]
    assert status == "blocked"
    assert "disabled" in error


def test_disabled_gate_does_not_duplicate_an_already_active_job(monkeypatch) -> None:
    # Debounce still wins over the disabled check — an active job (e.g. from
    # a moment when the flag was on) is reused rather than double-finished.
    job_store = _patch_job_store(monkeypatch, auto_chain_enabled=False)
    job_store.create("existing_job", "auto_chain", f"workspace_{WS}", WS)
    job_store.jobs["existing_job"]["status"] = "running"
    bg = FakeBackgroundTasks()

    job_id = chain_jobs.start_chain(DSN, WS, bg)

    assert job_id == "existing_job"
    assert job_store.finish_calls == []
    assert bg.tasks == []


# ── trigger_chain_from_brief ─────────────────────────────────────────────

def test_trigger_chain_from_brief_blocks_on_invalid_intent(monkeypatch) -> None:
    job_store = _patch_job_store(monkeypatch)
    intent_store = FakeIntentStore(DSN, WS)
    monkeypatch.setattr(chain_jobs, "IntentStore", lambda dsn, ws: intent_store)
    bg = FakeBackgroundTasks()

    job_id = chain_jobs.trigger_chain_from_brief(DSN, WS, {"domain": "", "aim": ""}, bg)

    assert intent_store.saved and intent_store.saved[0].validation_status == "invalid"
    job_id, run_id, status, error = job_store.finish_calls[0]
    assert status == "blocked"
    assert bg.tasks == []


def test_trigger_chain_from_brief_starts_chain_on_valid_intent(monkeypatch) -> None:
    _patch_job_store(monkeypatch)
    intent_store = FakeIntentStore(DSN, WS)
    monkeypatch.setattr(chain_jobs, "IntentStore", lambda dsn, ws: intent_store)
    bg = FakeBackgroundTasks()

    job_id = chain_jobs.trigger_chain_from_brief(
        DSN, WS, {"domain": "sales", "aim": "understand renewals"}, bg)

    assert intent_store.saved and intent_store.saved[0].validation_status == "valid"
    assert len(bg.tasks) == 1
    fn, args, kwargs = bg.tasks[0]
    assert fn is chain_jobs.run_auto_chain
    assert args == (DSN, WS, job_id)


# ── aryx.intent.from_brief — pure mapping, no DB ────────────────────────────

def test_brief_to_intent_maps_domain_and_aim() -> None:
    req = brief_to_intent_request({"domain": "sales", "aim": "understand renewals"}, WS)
    assert req.domain == "sales"
    assert req.objective == "understand renewals"


def test_brief_to_intent_uses_first_role_as_audience() -> None:
    req = brief_to_intent_request(
        {"domain": "sales", "aim": "x", "roles": ["Sales Manager", "Analyst"]}, WS)
    assert req.target_audience == "Sales Manager"


def test_brief_to_intent_no_roles_leaves_audience_blank() -> None:
    req = brief_to_intent_request({"domain": "sales", "aim": "x"}, WS)
    assert req.target_audience == ""


def test_brief_to_intent_uses_first_source_doc_as_uploaded_file() -> None:
    req = brief_to_intent_request(
        {"domain": "sales", "aim": "x", "source_docs": ["contracts.csv", "notes.pdf"]}, WS)
    assert req.uploaded_file == "contracts.csv"


def test_brief_to_intent_synthesizes_marker_when_no_source_docs() -> None:
    req = brief_to_intent_request({"domain": "sales", "aim": "x"}, WS)
    assert req.uploaded_file == f"brief:workspace_{WS}"


def test_brief_to_intent_feeds_capture_intent_and_validates() -> None:
    req = brief_to_intent_request({"domain": "sales", "aim": "understand renewals"}, WS)
    intent = capture_intent(req)
    assert intent.validation_status == "valid"
    assert intent.domain == "sales"
    assert intent.objective == "understand renewals"


def test_empty_brief_produces_invalid_capture() -> None:
    req = brief_to_intent_request({}, WS)
    intent = capture_intent(req)
    assert intent.validation_status == "invalid"
    assert any("domain" in e for e in intent.errors)
    assert any("objective" in e for e in intent.errors)
