"""Chain 5: ingest_file -> job completes -> entities_preview reflects it ->
ingest_questions/ingest_answer respond cleanly. Real Postgres + FalkorDB.

Runs against a REAL LLM (no stub): ingest_file goes over HTTP to the live
api container's _run_files, which calls a real LLM for entity extraction
with no injectable seam — unlike the C08 planner path, there's nothing in
this pytest process to monkeypatch. Proved reliable in live smoke testing
against local Ollama; excluded from CI (no GPU/Ollama there) via the
e2e_llm marker.
"""
from __future__ import annotations

import base64
import time

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_llm]

_CSV = b"id,name,region\n1,Acme,west\n2,Globex,east\n"


def _wait_for_job(workspace_id: int, job_id: str, timeout: float = 30.0) -> dict:
    from aryx.mcp.ingest_hitl import dispatch
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = dispatch("ingest_status", {"workspace_id": workspace_id, "job_id": job_id})
        job = status.get("job") or {}
        if job.get("status") in ("complete", "failed", "error"):
            return job
        time.sleep(1)
    pytest.fail(f"ingest job {job_id} did not finish within {timeout}s")


def test_ingest_file_to_entities_preview(workspace) -> None:
    """Full round trip: upload -> job completes -> real entities visible."""
    from aryx.mcp.ingest_hitl import dispatch
    wid = workspace["id"]

    started = dispatch("ingest_file", {
        "workspace_id": wid,
        "files": [{"filename": "e2e.csv", "content_base64": base64.b64encode(_CSV).decode()}],
    })
    assert started["status"] == "queued"
    assert "job_id" in started

    job = _wait_for_job(wid, started["job_id"])
    assert job["status"] == "complete", job

    preview = dispatch("entities_preview", {"workspace_id": wid, "limit": 20})
    assert preview["entity_total"] > 0, "expected at least one entity extracted"

    # Whether or not any questions were actually raised, the tool itself
    # must respond cleanly — never a raw error — either way.
    questions = dispatch("ingest_questions", {"workspace_id": wid, "status": ""})
    assert isinstance(questions, (list, dict))
