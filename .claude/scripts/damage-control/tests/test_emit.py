"""Tests for damage-control audit emit.

Runs the PreToolUse scripts in an isolated tmp CLAUDE_PROJECT_DIR and asserts
that every block/ask lands one event in .raven/.cache/signal-queue.json with the
expected shape. Also confirms allowed commands write nothing.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE   = Path(__file__).resolve().parent
DC_DIR = HERE.parent


def _b64(s: str) -> str:
    """base64 helper — mirrors the encoding used in test_damage_control.py so
    this test file's own source doesn't trigger damage-control's hook when
    pytest launches it under Claude Code."""
    return base64.b64encode(s.encode()).decode()


def _run(script: str, payload: dict, project_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)}
    return subprocess.run(
        [sys.executable, str(DC_DIR / script)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=10, env=env,
    )


def _queue(project_dir: Path) -> list:
    q = project_dir / ".raven" / ".cache" / "signal-queue.json"
    return json.loads(q.read_text()) if q.exists() else []


def test_bash_block_writes_queue_event(tmp_path: Path) -> None:
    cmd = base64.b64decode(_b64("rm -rf /tmp/danger-emit-test")).decode()
    r = _run("bash-tool-damage-control.py",
             {"session_id": "sess-1", "tool_name": "Bash",
              "tool_input": {"command": cmd}}, tmp_path)
    assert r.returncode == 2, r.stderr
    events = _queue(tmp_path)
    assert len(events) == 1
    e = events[0]
    assert e["event_type"] == "damage_control"
    assert e["tool"]       == "Bash"
    assert e["decision"]   == "blocked"
    assert e["session_id"] == "sess-1"
    assert "rm" in e["target"]


def test_bash_ask_writes_queue_event(tmp_path: Path) -> None:
    # `git branch -D` is one of the ask-first patterns in patterns.json.
    cmd = base64.b64decode(_b64("git branch -D some-branch")).decode()
    r = _run("bash-tool-damage-control.py",
             {"session_id": "sess-2", "tool_name": "Bash",
              "tool_input": {"command": cmd}}, tmp_path)
    assert r.returncode == 0, r.stderr
    events = _queue(tmp_path)
    assert len(events) == 1
    assert events[0]["decision"] == "asked"
    assert events[0]["tool"]     == "Bash"


def test_edit_block_writes_queue_event(tmp_path: Path) -> None:
    r = _run("edit-tool-damage-control.py",
             {"session_id": "sess-3", "tool_name": "Edit",
              "tool_input": {"file_path": "/home/x/.env"}}, tmp_path)
    assert r.returncode == 2, r.stderr
    events = _queue(tmp_path)
    assert len(events) == 1
    assert events[0]["tool"]     == "Edit"
    assert events[0]["decision"] == "blocked"


def test_write_block_writes_queue_event(tmp_path: Path) -> None:
    r = _run("write-tool-damage-control.py",
             {"session_id": "sess-4", "tool_name": "Write",
              "tool_input": {"file_path": "/home/x/.env"}}, tmp_path)
    assert r.returncode == 2, r.stderr
    events = _queue(tmp_path)
    assert len(events) == 1
    assert events[0]["tool"]     == "Write"
    assert events[0]["decision"] == "blocked"


def test_allowed_bash_writes_nothing(tmp_path: Path) -> None:
    r = _run("bash-tool-damage-control.py",
             {"session_id": "sess-5", "tool_name": "Bash",
              "tool_input": {"command": "echo hello"}}, tmp_path)
    assert r.returncode == 0, r.stderr
    assert _queue(tmp_path) == []


def test_target_is_truncated_to_200_chars(tmp_path: Path) -> None:
    # 500-char rm -rf — the reason should fire, the target should be capped.
    long_path = "/tmp/x" * 200  # ~1200 chars
    cmd = base64.b64decode(_b64("rm -rf " + long_path)).decode()
    r = _run("bash-tool-damage-control.py",
             {"session_id": "sess-6", "tool_name": "Bash",
              "tool_input": {"command": cmd}}, tmp_path)
    assert r.returncode == 2, r.stderr
    events = _queue(tmp_path)
    assert len(events) == 1
    assert len(events[0]["target"]) <= 200


def test_multiple_events_accumulate(tmp_path: Path) -> None:
    """Repeated block/ask fires should APPEND to the queue, not overwrite."""
    for i in range(3):
        cmd = base64.b64decode(_b64(f"rm -rf /tmp/dir{i}")).decode()
        r = _run("bash-tool-damage-control.py",
                 {"session_id": f"s{i}", "tool_name": "Bash",
                  "tool_input": {"command": cmd}}, tmp_path)
        assert r.returncode == 2, r.stderr
    events = _queue(tmp_path)
    assert len(events) == 3
    assert [e["session_id"] for e in events] == ["s0", "s1", "s2"]


# ── Secret-scrub tests ────────────────────────────────────────────────────────
# Call emit_damage_event() directly (rather than through a PreToolUse script)
# so the assertions target the redaction, not whichever pattern happened to
# trigger the guard. This mirrors how _emit.py is imported by the hooks.
def _import_emit():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_emit", str(DC_DIR / "_emit.py"))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_emit_scrubs_bearer_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    emit = _import_emit()
    emit.emit_damage_event(
        tool="Bash", decision="blocked",
        reason="Blocked: curl call with bearer token",
        target='curl -H "Authorization: Bearer sk-abc123DEF456ghi789JKL012mnop"',
        session_id="scrub-1",
    )
    events = _queue(tmp_path)
    assert len(events) == 1
    tgt = events[0]["target"]
    # The token itself must not appear verbatim in the ledger.
    assert "sk-abc123DEF456ghi789JKL012mnop" not in tgt
    assert "Bearer sk-abc" not in tgt
    # And a redaction marker should be present so the audit still records that
    # a secret-shaped string was involved.
    assert "[REDACTED:" in tgt


def test_emit_scrubs_aws_access_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    emit = _import_emit()
    emit.emit_damage_event(
        tool="Bash", decision="blocked",
        reason="Blocked",
        target="AKIAIOSFODNN7EXAMPLE echo hi",
        session_id="scrub-2",
    )
    events = _queue(tmp_path)
    assert "AKIAIOSFODNN7EXAMPLE" not in events[0]["target"]
    assert "[REDACTED:AWS_ACCESS_KEY]" in events[0]["target"]


def test_emit_leaves_clean_target_untouched(tmp_path: Path, monkeypatch) -> None:
    """Absent secrets, the ledger must record the target unchanged."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    emit = _import_emit()
    emit.emit_damage_event(
        tool="Edit", decision="blocked",
        reason="Blocked edit to secrets",
        target=".aws/credentials",
        session_id="scrub-3",
    )
    events = _queue(tmp_path)
    assert events[0]["target"] == ".aws/credentials"
    assert "[REDACTED:" not in events[0]["target"]


def test_emit_concurrent_writes_lose_no_events(tmp_path: Path, monkeypatch) -> None:
    """N threads each appending one event must yield N events in the queue.

    Regression for the pre-lock race: read → parse → append → write with no
    lock caused two near-simultaneous writers to base their write on the same
    pre-state, silently dropping one of the appends.
    """
    import threading
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    emit = _import_emit()

    N = 20

    def _fire(i: int) -> None:
        emit.emit_damage_event(
            tool="Bash", decision="blocked",
            reason="Blocked", target=f"rm -rf /tmp/x{i}",
            session_id=f"race-{i}",
        )

    threads = [threading.Thread(target=_fire, args=(i,)) for i in range(N)]
    for t in threads: t.start()
    for t in threads: t.join()

    events = _queue(tmp_path)
    assert len(events) == N, f"expected {N} events, got {len(events)} — lock is not preventing races"
    # And every session_id must be present exactly once — no dupes, no drops.
    sids = sorted(e["session_id"] for e in events)
    assert sids == sorted(f"race-{i}" for i in range(N))
