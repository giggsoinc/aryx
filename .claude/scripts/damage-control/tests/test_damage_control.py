"""Tests for damage-control hooks.

Runs the three PreToolUse scripts as subprocesses (matches how they run in
production) and asserts the exit code + stderr for a corpus of representative
inputs. Also exercises pure-logic units (`match_path`, `glob_to_regex`,
`check_command`) via direct import.

Exit-code contract:
  0 = allow (or ask via JSON output)
  2 = block (or fail-safe on unreadable config)
  1 = script-level error (invalid stdin JSON, etc.)
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
DC_DIR = HERE.parent


def _load_module(script_name: str):
    """Load a hyphenated script as a module without running its main()."""
    path = DC_DIR / script_name
    spec = importlib.util.spec_from_file_location(
        script_name.replace("-", "_").replace(".py", ""),
        path,
    )
    mod = importlib.util.module_from_spec(spec)
    # Guard against main() executing at import
    src = path.read_text()
    if 'if __name__ == "__main__":' in src:
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)
    return mod


bash_mod = _load_module("bash-tool-damage-control.py")
edit_mod = _load_module("edit-tool-damage-control.py")
write_mod = _load_module("write-tool-damage-control.py")


def _b64(s: str) -> str:
    """Encode a payload so pytest source doesn't trip damage-control's own hook."""
    return base64.b64encode(s.encode()).decode()


def _run(script: str, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DC_DIR / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


# ---------- bash firewall — hard blocks ----------

# Commands are base64-encoded because damage-control's OWN hook (which fires
# on the pytest process's Bash tool call) would otherwise flag these literals.
BLOCK_BASH = [
    (_b64("rm -rf /tmp/foo"),             "rm -rf"),
    (_b64("sudo rm /etc/hosts"),          "sudo rm"),
    (_b64("chmod 777 secrets.json"),      "chmod 777"),
    (_b64("git reset --hard HEAD"),       "git reset --hard"),
    (_b64("git push origin main --force"),"git push --force"),
    (_b64("git filter-branch --tree-filter foo HEAD"), "git filter-branch"),
    (_b64("terraform destroy -auto-approve"), "terraform destroy"),
    (_b64("kubectl delete namespace prod"),   "kubectl delete namespace"),
    (_b64("aws s3 rm s3://bucket --recursive"), "aws s3 rm --recursive"),
    (_b64("gcloud projects delete my-project"), "gcloud projects delete"),
    (_b64("DROP TABLE users;"),           "DROP TABLE"),
    (_b64("TRUNCATE TABLE payments;"),    "TRUNCATE TABLE"),
    (_b64("DELETE FROM audit_log;"),      "DELETE without WHERE"),
    (_b64("redis-cli FLUSHALL"),          "FLUSHALL"),
    (_b64("find . -name '*.tmp' -delete"), "find -delete"),
    (_b64("find . -name '*.tmp' -exec rm {} ;"), "find -exec rm"),
    (_b64("find . -name '*.tmp' | xargs rm"), "xargs rm"),
    (_b64("gh repo delete Giggso-Inc/raven-enterprise"), "gh repo delete"),
    (_b64("docker volume rm my_data"),    "docker volume rm"),
    (_b64("npm unpublish some-package@1.0.0"), "npm unpublish"),
]


@pytest.mark.parametrize("cmd_b64,label", BLOCK_BASH)
def test_bash_hard_block(cmd_b64: str, label: str) -> None:
    cmd = base64.b64decode(cmd_b64).decode()
    r = _run("bash-tool-damage-control.py",
             {"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert r.returncode == 2, f"{label!r} should block. stderr={r.stderr}"
    assert "SECURITY" in r.stderr


# ---------- bash firewall — ask-first (exit 0 + JSON) ----------

ASK_BASH = [
    (_b64("git stash drop stash@{0}"),  "git stash drop"),
    (_b64("git branch -D feature/foo"), "git branch -D"),
    (_b64("git push origin --delete old-branch"), "git push --delete"),
    (_b64("git restore ."),             "git restore ."),
]


@pytest.mark.parametrize("cmd_b64,label", ASK_BASH)
def test_bash_ask(cmd_b64: str, label: str) -> None:
    cmd = base64.b64decode(cmd_b64).decode()
    r = _run("bash-tool-damage-control.py",
             {"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert r.returncode == 0, f"{label!r} should ask (exit 0). stderr={r.stderr}"
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


# ---------- bash firewall — allow ----------

ALLOW_BASH = [
    "ls -la",
    "echo hello world",
    "cat README.md",
    "git status",
    "git push origin main --force-with-lease",  # explicitly still allowed
    "npm install",
    "pytest tests/",
]


@pytest.mark.parametrize("cmd", ALLOW_BASH)
def test_bash_allow(cmd: str) -> None:
    r = _run("bash-tool-damage-control.py",
             {"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert r.returncode == 0, f"{cmd!r} should be allowed. stderr={r.stderr}"


# ---------- edit / write — path checks ----------

BLOCK_EDIT_WRITE = [
    "/home/dev/repo/.env",
    "/home/dev/repo/.env.production",
    "/home/dev/repo/config.env",
    "/home/dev/keys/server.pem",
    "/home/dev/certs/private.key",
    "/home/dev/creds/firebase-adminsdk-abc.json",
    "/home/dev/repo/serviceAccountKey.json",
    "/home/dev/repo/terraform.tfstate",
]


# Known limitation: literal (non-glob) zero-access entries like "dump.sql"
# use prefix matching, so "/tmp/dump.sql" is NOT caught. Users who need to
# block by basename should convert the entry to a glob (e.g. "*.dump", "dump*.sql").
# Documented in docs/DAMAGE-CONTROL.md → Limitations & known trade-offs.
LITERAL_BASENAME_KNOWN_GAP = [
    "/tmp/dump.sql",
    "/tmp/backup.sql",
]


@pytest.mark.parametrize("path", LITERAL_BASENAME_KNOWN_GAP)
def test_edit_literal_basename_known_gap(path: str) -> None:
    """Documents the literal-basename prefix-match limitation as a known gap."""
    r = _run("edit-tool-damage-control.py",
             {"tool_name": "Edit", "tool_input": {"file_path": path}})
    # Currently PASSES the hook (returncode 0). If a future patch fixes basename
    # matching, invert this to expect returncode == 2 and remove the gap doc.
    assert r.returncode == 0


@pytest.mark.parametrize("path", BLOCK_EDIT_WRITE)
def test_edit_blocks_secret_paths(path: str) -> None:
    r = _run("edit-tool-damage-control.py",
             {"tool_name": "Edit", "tool_input": {"file_path": path}})
    assert r.returncode == 2, f"{path} should be blocked. stderr={r.stderr}"


@pytest.mark.parametrize("path", BLOCK_EDIT_WRITE)
def test_write_blocks_secret_paths(path: str) -> None:
    r = _run("write-tool-damage-control.py",
             {"tool_name": "Write", "tool_input": {"file_path": path}})
    assert r.returncode == 2, f"{path} should be blocked. stderr={r.stderr}"


ALLOW_EDIT_WRITE = [
    "/home/dev/repo/src/main.py",
    "/home/dev/repo/README.md",
    "/home/dev/repo/tests/test_foo.py",
    "/tmp/scratch.txt",
]


@pytest.mark.parametrize("path", ALLOW_EDIT_WRITE)
def test_edit_allows_normal_paths(path: str) -> None:
    r = _run("edit-tool-damage-control.py",
             {"tool_name": "Edit", "tool_input": {"file_path": path}})
    assert r.returncode == 0, f"{path} should be allowed. stderr={r.stderr}"


# ---------- non-matching tool_name should no-op ----------

def test_bash_hook_ignores_non_bash_tool() -> None:
    r = _run("bash-tool-damage-control.py",
             {"tool_name": "Read", "tool_input": {"file_path": "/tmp/foo"}})
    assert r.returncode == 0


def test_edit_hook_ignores_non_edit_tool() -> None:
    r = _run("edit-tool-damage-control.py",
             {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert r.returncode == 0


# ---------- unit tests: pure logic ----------

def test_glob_to_regex_star_matches_basename() -> None:
    import re as _re
    r = bash_mod.glob_to_regex("*.pem")
    assert _re.search(r, "server.pem", _re.IGNORECASE)
    assert not _re.search(r, "server.txt", _re.IGNORECASE)


def test_glob_to_regex_character_class_preserved() -> None:
    """Regression: '[' used to be escaped as literal, breaking char classes."""
    import re as _re
    r = bash_mod.glob_to_regex("secret[s0-9].json")
    assert _re.search(r, "secrets.json", _re.IGNORECASE)
    assert _re.search(r, "secret1.json", _re.IGNORECASE)
    assert not _re.search(r, "secretx.json", _re.IGNORECASE)


def test_glob_to_regex_negated_character_class() -> None:
    import re as _re
    r = bash_mod.glob_to_regex("cfg[!bak].json")
    # Note: matched inside a longer string; glob '[!bak]' -> regex '[^bak]'
    assert _re.search(r, "cfgx.json", _re.IGNORECASE)
    assert not _re.search(r, "cfgb.json", _re.IGNORECASE)


def test_glob_to_regex_unterminated_bracket_is_literal() -> None:
    import re as _re
    r = bash_mod.glob_to_regex("foo[.txt")
    # Unterminated '[' escaped as literal — matches literal '[' in string
    assert _re.search(r, "foo[.txt", _re.IGNORECASE)


def test_match_path_glob_basename() -> None:
    assert edit_mod.match_path("/home/x/y/server.pem", "*.pem") is True
    assert edit_mod.match_path("/home/x/y/server.txt", "*.pem") is False


def test_match_path_env_dot_glob() -> None:
    # .env.* pattern used in real patterns.json
    assert edit_mod.match_path("/home/x/y/.env.production", ".env.*") is True


def test_match_path_literal_prefix() -> None:
    ssh_target = os.path.expanduser("~/.ssh/id_rsa")
    assert edit_mod.match_path(ssh_target, "~/.ssh/") is True
    assert edit_mod.match_path("/tmp/foo", "~/.ssh/") is False


# ---------- config error handling — fail-closed ----------

def test_config_missing_fails_open_bootstrap(tmp_path, monkeypatch) -> None:
    """When patterns.json doesn't exist, hook should allow (bootstrap case)."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    # Point the script's cwd to a location where no patterns.json exists
    # Copy the script into the tmp dir so its Path(__file__).parent lookup misses
    script_copy = tmp_path / "bash-tool-damage-control.py"
    script_copy.write_bytes((DC_DIR / "bash-tool-damage-control.py").read_bytes())
    r = subprocess.run(
        [sys.executable, str(script_copy)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    assert "bootstrap" in r.stderr.lower() or r.stderr == "" or "not found" in r.stderr.lower()


def test_config_invalid_json_fails_closed(tmp_path) -> None:
    """When patterns.json exists but is unreadable, hook must EXIT 2 (fail-safe)."""
    bad = tmp_path / "patterns.json"
    bad.write_text("{ this is not valid json")
    script_copy = tmp_path / "bash-tool-damage-control.py"
    script_copy.write_bytes((DC_DIR / "bash-tool-damage-control.py").read_bytes())
    r = subprocess.run(
        [sys.executable, str(script_copy)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 2, f"Corrupted config should fail-closed. stderr={r.stderr}"
    assert "SECURITY" in r.stderr and "fail-safe" in r.stderr


def test_config_non_object_fails_closed(tmp_path) -> None:
    """patterns.json with an array or scalar root must fail-closed."""
    bad = tmp_path / "patterns.json"
    bad.write_text("[]")
    script_copy = tmp_path / "bash-tool-damage-control.py"
    script_copy.write_bytes((DC_DIR / "bash-tool-damage-control.py").read_bytes())
    r = subprocess.run(
        [sys.executable, str(script_copy)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 2, f"Non-object config should fail-closed. stderr={r.stderr}"


# ---------- invalid stdin ----------

def test_invalid_stdin_json() -> None:
    r = subprocess.run(
        [sys.executable, str(DC_DIR / "bash-tool-damage-control.py")],
        input="not json at all",
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 1
    assert "Invalid JSON" in r.stderr
