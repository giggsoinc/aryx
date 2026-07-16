#!/usr/bin/env python3
"""
Raven Damage-Control — Edit tool firewall (PreToolUse)
======================================================

Blocks edits to protected files.
Loads zeroAccessPaths and readOnlyPaths from patterns.json.

Exit codes:
  0 = Allow edit
  2 = Block edit
"""

import json
import sys
import os
import fnmatch
from pathlib import Path
from typing import Dict, Any, Tuple

# Ensure sibling _emit.py is importable regardless of how the hook was launched.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _emit import emit_damage_event
except Exception:
    def emit_damage_event(**_kwargs):  # type: ignore
        return


def is_glob_pattern(pattern: str) -> bool:
    return '*' in pattern or '?' in pattern or '[' in pattern


def match_path(file_path: str, pattern: str) -> bool:
    expanded_pattern = os.path.expanduser(pattern)
    normalized = os.path.normpath(file_path)
    expanded_normalized = os.path.expanduser(normalized)

    if is_glob_pattern(pattern):
        basename = os.path.basename(expanded_normalized).lower()
        pattern_lower = pattern.lower()
        expanded_pattern_lower = expanded_pattern.lower()
        if fnmatch.fnmatch(basename, expanded_pattern_lower):
            return True
        if fnmatch.fnmatch(basename, pattern_lower):
            return True
        if fnmatch.fnmatch(expanded_normalized.lower(), expanded_pattern_lower):
            return True
        return False
    else:
        if expanded_normalized.startswith(expanded_pattern) or expanded_normalized == expanded_pattern.rstrip('/'):
            return True
        return False


def get_config_path() -> Path:
    script_dir = Path(__file__).parent
    local = script_dir / "patterns.json"
    if local.exists():
        return local

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        for sub in ("scripts/damage-control", "hooks/damage-control"):
            cand = Path(project_dir) / ".claude" / sub / "patterns.json"
            if cand.exists():
                return cand
        legacy_yaml = Path(project_dir) / ".claude" / "hooks" / "damage-control" / "patterns.yaml"
        if legacy_yaml.exists():
            return legacy_yaml

    return local


def load_config() -> Dict[str, Any]:
    """Load config from patterns.json (or legacy patterns.yaml).

    Fails CLOSED (exits 2) if a config file exists but is unreadable or invalid.
    Fails OPEN (empty policy) only when no config file exists — bootstrap case.
    """
    config_path = get_config_path()
    if not config_path.exists():
        return {"zeroAccessPaths": [], "readOnlyPaths": []}

    try:
        with open(config_path, "r") as f:
            if config_path.suffix == ".json":
                data = json.load(f)
            else:
                try:
                    import yaml
                except ImportError:
                    print(f"SECURITY: damage-control legacy config at {config_path} needs PyYAML — blocking as fail-safe", file=sys.stderr)
                    sys.exit(2)
                data = yaml.safe_load(f)
        if not isinstance(data, dict):
            print(f"SECURITY: damage-control config {config_path} is not an object — blocking as fail-safe", file=sys.stderr)
            sys.exit(2)
        return data
    except SystemExit:
        raise
    except Exception as e:
        print(f"SECURITY: damage-control config unreadable ({config_path}: {e}) — blocking as fail-safe", file=sys.stderr)
        sys.exit(2)


def check_path(file_path: str, config: Dict[str, Any]) -> Tuple[bool, str]:
    for zero_path in config.get("zeroAccessPaths", []):
        if match_path(file_path, zero_path):
            return True, f"zero-access path {zero_path} (no operations allowed)"
    for readonly in config.get("readOnlyPaths", []):
        if match_path(file_path, readonly):
            return True, f"read-only path {readonly}"
    return False, ""


def main() -> None:
    config = load_config()

    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    session_id = input_data.get("session_id", "") or ""
    if tool_name != "Edit":
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    blocked, reason = check_path(file_path, config)
    if blocked:
        full_reason = f"Blocked edit to {reason}"
        emit_damage_event(
            tool="Edit", decision="blocked", reason=full_reason,
            target=file_path, session_id=session_id,
        )
        print(f"SECURITY: {full_reason}: {file_path}", file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
