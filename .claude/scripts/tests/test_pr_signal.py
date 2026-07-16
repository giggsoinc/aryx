#!/usr/bin/env python3
"""Unit tests for pr-signal.py — command guards, error guards, and emit atomicity."""

import importlib.util, json, sys, tempfile, threading, unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).parent.parent / "pr-signal.py"


def _load():
    spec = importlib.util.spec_from_file_location("pr_signal", SCRIPT)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ctx(command: str, is_error: bool = False, stdout: str = "") -> dict:
    resp: dict = {"isError": is_error} if is_error else {}
    if stdout:
        resp["stdout"] = stdout
    return {
        "tool_input":    {"command": command},
        "tool_response": resp,
    }


def _run(ctx: dict) -> list[str]:
    """Invoke main() with ctx on stdin and return list of emitted event types."""
    mod     = _load()
    emitted = []
    stdin   = StringIO(json.dumps(ctx))
    stdin.isatty = lambda: False  # type: ignore[method-assign]
    with patch.object(mod, "emit", side_effect=lambda t, url=None: emitted.append(t)):
        with patch("sys.stdin", stdin):
            try:
                mod.main()
            except SystemExit:
                pass
    return emitted


def _run_full(ctx: dict, origin: str | None = None) -> list[dict]:
    """Like _run but returns the full emitted events (event_type + url)."""
    mod     = _load()
    emitted: list[dict] = []
    stdin   = StringIO(json.dumps(ctx))
    stdin.isatty = lambda: False  # type: ignore[method-assign]
    def _capture(t, url=None):
        evt = {"event_type": t}
        if url:
            evt["url"] = url
        emitted.append(evt)
    with patch.object(mod, "emit", side_effect=_capture), \
         patch("sys.stdin", stdin), \
         patch.object(mod, "_origin_owner_repo", return_value=origin):
        try:
            mod.main()
        except SystemExit:
            pass
    return emitted


class TestPRCreate(unittest.TestCase):
    def test_creates_pr(self):
        self.assertEqual(_run(_ctx("gh pr create --title 'feat: x'")), ["pr_created"])

    def test_help_no_emit(self):
        self.assertEqual(_run(_ctx("gh pr create --help")), [])

    def test_dry_run_no_emit(self):
        self.assertEqual(_run(_ctx("gh pr create --dry-run")), [])

    def test_error_no_emit(self):
        self.assertEqual(_run(_ctx("gh pr create --title 'x'", is_error=True)), [])

    def test_uppercase_command_matched(self):
        # command is lowercased before matching
        self.assertEqual(_run(_ctx("GH PR Create --title 'x'")), ["pr_created"])


class TestPRReview(unittest.TestCase):
    def test_approve_emits(self):
        self.assertEqual(_run(_ctx("gh pr review 123 --approve")), ["pr_reviewed"])

    def test_comment_emits(self):
        self.assertEqual(_run(_ctx("gh pr review 123 --comment -b 'lgtm'")), ["pr_reviewed"])

    def test_request_changes_emits(self):
        self.assertEqual(_run(_ctx("gh pr review 123 --request-changes -b 'nits'")), ["pr_reviewed"])

    def test_interactive_review_emits(self):
        # bare `gh pr review 123` opens the interactive prompt; if the user submits
        # the review, gh exits 0 and we count it. Cancelled/failed runs come through
        # with isError=True (see test_error_no_emit) and are excluded.
        self.assertEqual(_run(_ctx("gh pr review 123")), ["pr_reviewed"])

    def test_help_no_emit(self):
        self.assertEqual(_run(_ctx("gh pr review --help")), [])

    def test_error_no_emit(self):
        self.assertEqual(_run(_ctx("gh pr review 123 --approve", is_error=True)), [])


class TestUnrelatedCommands(unittest.TestCase):
    def test_git_status(self):
        self.assertEqual(_run(_ctx("git status")), [])

    def test_gh_pr_list(self):
        self.assertEqual(_run(_ctx("gh pr list")), [])

    def test_gh_pr_view(self):
        # read-only subcommands must not trigger
        self.assertEqual(_run(_ctx("gh pr view 123")), [])


class TestEmitAtomicity(unittest.TestCase):
    def test_concurrent_emits_no_loss(self):
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            mod.SIGNAL_QUEUE_PATH = Path(tmp) / "signal-queue.json"
            threads = [threading.Thread(target=mod.emit, args=("pr_created",)) for _ in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            queue = json.loads(mod.SIGNAL_QUEUE_PATH.read_text())
            self.assertEqual(len(queue), 20, f"expected 20 events, got {len(queue)}")

    def test_emit_persists_url(self):
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            mod.SIGNAL_QUEUE_PATH = Path(tmp) / "signal-queue.json"
            mod.emit("pr_created", "https://github.com/foo/bar/pull/9")
            queue = json.loads(mod.SIGNAL_QUEUE_PATH.read_text())
            self.assertEqual(queue, [{"event_type": "pr_created",
                                      "url": "https://github.com/foo/bar/pull/9"}])


class TestPRUrlCapture(unittest.TestCase):
    def test_pr_create_url_from_stdout(self):
        ctx = _ctx("gh pr create --title 'feat: x'",
                   stdout="Warming up...\nhttps://github.com/acme/widget/pull/42\n")
        self.assertEqual(
            _run_full(ctx),
            [{"event_type": "pr_created", "url": "https://github.com/acme/widget/pull/42"}],
        )

    def test_pr_create_no_url_when_stdout_empty(self):
        # Still emit the count event even when the URL can't be parsed.
        self.assertEqual(_run_full(_ctx("gh pr create --title 'x'")),
                         [{"event_type": "pr_created"}])

    def test_pr_review_url_built_from_origin(self):
        ctx = _ctx("gh pr review 123 --approve")
        self.assertEqual(
            _run_full(ctx, origin="acme/widget"),
            [{"event_type": "pr_reviewed", "url": "https://github.com/acme/widget/pull/123"}],
        )

    def test_pr_review_no_url_without_origin(self):
        self.assertEqual(_run_full(_ctx("gh pr review 7 --comment -b 'lgtm'"), origin=None),
                         [{"event_type": "pr_reviewed"}])


if __name__ == "__main__":
    unittest.main()
