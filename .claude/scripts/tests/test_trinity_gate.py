"""Unit tests for trinity-gate.py — route detection, path helpers, dedup, error paths."""

import importlib.util, io, json, subprocess, sys, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRIPT = Path(__file__).parent.parent / "trinity-gate.py"


def _load():
    spec = importlib.util.spec_from_file_location("trinity_gate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _capture_emit(mod, fn, *args, **kwargs):
    """Run fn(*args, **kwargs) and return the dict written to stdout via emit()."""
    buf = io.StringIO()
    with patch.object(sys, "stdout", buf):
        fn(*args, **kwargs)
    out = buf.getvalue().strip()
    return json.loads(out) if out else None


# ── Detect ────────────────────────────────────────────────────────────────────

class TestDetect(unittest.TestCase):
    def setUp(self):
        self.mod = _load()

    def test_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _capture_emit(self.mod, self.mod.cmd_detect)
        self.assertFalse(result["found"])
        self.assertIn("git not found", result["error"])

    def test_git_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=15)):
            result = _capture_emit(self.mod, self.mod.cmd_detect)
        self.assertFalse(result["found"])
        self.assertIn("timed out", result["error"])

    def test_no_endpoints_in_diff(self):
        mock = MagicMock()
        mock.stdout = "diff --git a/main.py b/main.py\n+def hello(): pass\n"
        with patch("subprocess.run", return_value=mock):
            result = _capture_emit(self.mod, self.mod.cmd_detect)
        self.assertFalse(result["found"])
        self.assertEqual(result["count"], 0)

    def test_detects_fastapi_get(self):
        diff = (
            "diff --git a/router.py b/router.py\n"
            '+@router.get("/api/items")\n'
            "+async def list_items(): pass\n"
        )
        mock = MagicMock()
        mock.stdout = diff
        with patch("subprocess.run", return_value=mock):
            result = _capture_emit(self.mod, self.mod.cmd_detect)
        self.assertTrue(result["found"])
        self.assertEqual(result["count"], 1)
        ep = result["endpoints"][0]
        self.assertEqual(ep["method"], "GET")
        self.assertEqual(ep["path"], "/api/items")
        self.assertEqual(ep["framework"], "fastapi")

    def test_detects_fastapi_post(self):
        diff = (
            "diff --git a/router.py b/router.py\n"
            '+@app.post("/api/pay")\n'
        )
        mock = MagicMock()
        mock.stdout = diff
        with patch("subprocess.run", return_value=mock):
            result = _capture_emit(self.mod, self.mod.cmd_detect)
        self.assertTrue(result["found"])
        self.assertEqual(result["endpoints"][0]["method"], "POST")

    def test_detects_flask_route(self):
        diff = (
            "diff --git a/views.py b/views.py\n"
            '+@app.route("/submit")\n'
        )
        mock = MagicMock()
        mock.stdout = diff
        with patch("subprocess.run", return_value=mock):
            result = _capture_emit(self.mod, self.mod.cmd_detect)
        self.assertTrue(result["found"])

    def test_ignores_non_py_files(self):
        diff = (
            "diff --git a/README.md b/README.md\n"
            '+@app.get("/not-a-route")\n'
        )
        mock = MagicMock()
        mock.stdout = diff
        with patch("subprocess.run", return_value=mock):
            result = _capture_emit(self.mod, self.mod.cmd_detect)
        self.assertFalse(result["found"])


# ── Dedup ─────────────────────────────────────────────────────────────────────

class TestDedup(unittest.TestCase):
    def setUp(self):
        self.mod = _load()

    def _route(self, method="GET", path="/items", file="a.py"):
        return {"method": method, "path": path, "file": file, "line": 1, "framework": "fastapi"}

    def test_removes_exact_duplicates(self):
        routes = [self._route(), self._route(), self._route(method="POST")]
        self.assertEqual(len(self.mod._dedup(routes)), 2)

    def test_keeps_same_path_different_file(self):
        routes = [self._route(file="a.py"), self._route(file="b.py")]
        self.assertEqual(len(self.mod._dedup(routes)), 2)

    def test_empty_input(self):
        self.assertEqual(self.mod._dedup([]), [])


# ── Path helpers ──────────────────────────────────────────────────────────────

class TestPathHelpers(unittest.TestCase):
    def setUp(self):
        self.mod = _load()

    def test_path_set_simple(self):
        result = self.mod._path_set({"message": "old"}, "message", "injected")
        self.assertEqual(result["message"], "injected")

    def test_path_set_nested(self):
        obj = {"messages": [{"content": "old"}]}
        result = self.mod._path_set(obj, "messages[0][content]", "injected")
        self.assertEqual(result["messages"][0]["content"], "injected")

    def test_path_set_does_not_mutate_original(self):
        obj = {"key": "original"}
        self.mod._path_set(obj, "key", "new")
        self.assertEqual(obj["key"], "original")

    def test_path_get_simple(self):
        self.assertEqual(self.mod._path_get({"response": "hello"}, "response"), "hello")

    def test_path_get_nested(self):
        obj = {"choices": [{"message": {"content": "hi"}}]}
        self.assertEqual(self.mod._path_get(obj, "choices[0][message][content]"), "hi")


# ── run-prompts error paths ───────────────────────────────────────────────────

class TestRunPromptsErrors(unittest.TestCase):
    def setUp(self):
        self.mod = _load()

    def test_invalid_prompts_json(self):
        result = _capture_emit(
            self.mod, self.mod.cmd_run_prompts,
            url="http://localhost/api", method="POST",
            prompts_json="not-valid-json",
        )
        self.assertIn("error", result)

    def test_missing_prompts_file(self):
        result = _capture_emit(
            self.mod, self.mod.cmd_run_prompts,
            url="http://localhost/api", method="POST",
            prompts_file="/nonexistent/trinity_test_prompts.json",
        )
        self.assertIn("error", result)


# ── stop-app error paths ──────────────────────────────────────────────────────

class TestStopApp(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.mod.PID_FILE = Path("/tmp/.nonexistent-trinity-pid-test")

    def test_stop_no_pid_no_file(self):
        result = _capture_emit(self.mod, self.mod.cmd_stop_app, pid=None)
        self.assertFalse(result["stopped"])
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
