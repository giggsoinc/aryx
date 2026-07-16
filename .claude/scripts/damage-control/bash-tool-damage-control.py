#!/usr/bin/env python3
"""
Raven Damage-Control — Bash tool firewall (PreToolUse)
======================================================

Blocks dangerous bash commands before execution.
Loads patterns from patterns.json (sibling file).

Exit codes:
  0 = Allow command (or JSON output with permissionDecision)
  2 = Block command (stderr fed back to Claude)

JSON output for ask patterns:
  {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                          "permissionDecision": "ask",
                          "permissionDecisionReason": "..."}}
"""

import json
import sys
import re
import os
from pathlib import Path
from typing import Tuple, List, Dict, Any

# Ensure sibling _emit.py is importable regardless of how the hook was launched.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _emit import emit_damage_event
except Exception:
    def emit_damage_event(**_kwargs):  # type: ignore
        return


def is_glob_pattern(pattern: str) -> bool:
    return '*' in pattern or '?' in pattern or '[' in pattern


def glob_to_regex(glob_pattern: str) -> str:
    """Convert a glob pattern to a regex fragment.

    Supports:
      *        -> any run of non-whitespace/non-slash chars
      ?        -> a single non-whitespace/non-slash char
      [abc]    -> a regex character class (passed through)
      [!abc]   -> negated class (glob syntax) -> [^abc]
      [...]    -> unterminated bracket is treated as literal '['
    """
    result = []
    i = 0
    n = len(glob_pattern)
    while i < n:
        char = glob_pattern[i]
        if char == '*':
            result.append(r'[^\s/]*')
            i += 1
        elif char == '?':
            result.append(r'[^\s/]')
            i += 1
        elif char == '[':
            # Find the closing ']' — if none, treat '[' as literal
            close = glob_pattern.find(']', i + 1)
            if close == -1:
                result.append(r'\[')
                i += 1
                continue
            body = glob_pattern[i + 1:close]
            # Glob '!' negation -> regex '^' negation
            if body.startswith('!'):
                body = '^' + body[1:]
            result.append('[' + body + ']')
            i = close + 1
        elif char in r'\.^$+{}|()':
            result.append('\\' + char)
            i += 1
        else:
            result.append(char)
            i += 1
    return ''.join(result)


WRITE_PATTERNS = [
    (r'>\s*{path}', "write"),
    (r'\btee\s+(?!.*-a).*{path}', "write"),
]
APPEND_PATTERNS = [
    (r'>>\s*{path}', "append"),
    (r'\btee\s+-a\s+.*{path}', "append"),
    (r'\btee\s+.*-a.*{path}', "append"),
]
EDIT_PATTERNS = [
    (r'\bsed\s+-i.*{path}', "edit"),
    (r'\bperl\s+-[^\s]*i.*{path}', "edit"),
    (r'\bawk\s+-i\s+inplace.*{path}', "edit"),
]
MOVE_COPY_PATTERNS = [
    (r'\bmv\s+.*\s+{path}', "move"),
    (r'\bcp\s+.*\s+{path}', "copy"),
]
DELETE_PATTERNS = [
    (r'\brm\s+.*{path}', "delete"),
    (r'\bunlink\s+.*{path}', "delete"),
    (r'\brmdir\s+.*{path}', "delete"),
    (r'\bshred\s+.*{path}', "delete"),
]
PERMISSION_PATTERNS = [
    (r'\bchmod\s+.*{path}', "chmod"),
    (r'\bchown\s+.*{path}', "chown"),
    (r'\bchgrp\s+.*{path}', "chgrp"),
]
TRUNCATE_PATTERNS = [
    (r'\btruncate\s+.*{path}', "truncate"),
    (r':\s*>\s*{path}', "truncate"),
]

READ_ONLY_BLOCKED = (
    WRITE_PATTERNS + APPEND_PATTERNS + EDIT_PATTERNS +
    MOVE_COPY_PATTERNS + DELETE_PATTERNS + PERMISSION_PATTERNS + TRUNCATE_PATTERNS
)
NO_DELETE_BLOCKED = DELETE_PATTERNS


def get_config_path() -> Path:
    """Find patterns.json. Resolution order:
      1. Script's own directory (installed location: ~/.claude/scripts/damage-control/)
      2. $CLAUDE_PROJECT_DIR/.claude/scripts/damage-control/  (per-project install)
      3. $CLAUDE_PROJECT_DIR/.claude/hooks/damage-control/    (legacy dev location)
    """
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

    Fails CLOSED (exits 2) if a config file exists but is unreadable or invalid —
    a broken policy file must not silently disarm the firewall.

    Fails OPEN (returns empty policy) only when NO config file exists at all —
    the bootstrap case, so a fresh install before patterns.json lands doesn't
    lock the user out entirely.
    """
    config_path = get_config_path()
    if not config_path.exists():
        print(f"Warning: damage-control config not found at {config_path} — allowing (bootstrap)", file=sys.stderr)
        return {"bashToolPatterns": [], "zeroAccessPaths": [], "readOnlyPaths": [], "noDeletePaths": []}

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


def check_path_patterns(command: str, path: str, patterns: List[Tuple[str, str]], path_type: str) -> Tuple[bool, str]:
    if is_glob_pattern(path):
        glob_regex = glob_to_regex(path)
        for pattern_template, operation in patterns:
            try:
                cmd_prefix = pattern_template.replace("{path}", "")
                if cmd_prefix and re.search(cmd_prefix + glob_regex, command, re.IGNORECASE):
                    return True, f"Blocked: {operation} operation on {path_type} {path}"
            except re.error:
                continue
    else:
        expanded = os.path.expanduser(path)
        escaped_expanded = re.escape(expanded)
        escaped_original = re.escape(path)
        for pattern_template, operation in patterns:
            pattern_expanded = pattern_template.replace("{path}", escaped_expanded)
            pattern_original = pattern_template.replace("{path}", escaped_original)
            try:
                if re.search(pattern_expanded, command) or re.search(pattern_original, command):
                    return True, f"Blocked: {operation} operation on {path_type} {path}"
            except re.error:
                continue
    return False, ""


def check_command(command: str, config: Dict[str, Any]) -> Tuple[bool, bool, str]:
    """Returns (blocked, ask, reason)."""
    patterns = config.get("bashToolPatterns", [])
    zero_access_paths = config.get("zeroAccessPaths", [])
    read_only_paths = config.get("readOnlyPaths", [])
    no_delete_paths = config.get("noDeletePaths", [])

    for item in patterns:
        pattern = item.get("pattern", "")
        reason = item.get("reason", "Blocked by pattern")
        should_ask = item.get("ask", False)
        try:
            if re.search(pattern, command, re.IGNORECASE):
                if should_ask:
                    return False, True, reason
                return True, False, f"Blocked: {reason}"
        except re.error:
            continue

    for zero_path in zero_access_paths:
        if is_glob_pattern(zero_path):
            glob_regex = glob_to_regex(zero_path)
            try:
                if re.search(glob_regex, command, re.IGNORECASE):
                    return True, False, f"Blocked: zero-access pattern {zero_path} (no operations allowed)"
            except re.error:
                continue
        else:
            expanded = os.path.expanduser(zero_path)
            if re.search(re.escape(expanded), command) or re.search(re.escape(zero_path), command):
                return True, False, f"Blocked: zero-access path {zero_path} (no operations allowed)"

    for readonly in read_only_paths:
        blocked, reason = check_path_patterns(command, readonly, READ_ONLY_BLOCKED, "read-only path")
        if blocked:
            return True, False, reason

    for no_delete in no_delete_paths:
        blocked, reason = check_path_patterns(command, no_delete, NO_DELETE_BLOCKED, "no-delete path")
        if blocked:
            return True, False, reason

    return False, False, ""


def main() -> None:
    config = load_config()

    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading input: {e}", file=sys.stderr)
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    session_id = input_data.get("session_id", "") or ""
    if tool_name != "Bash":
        sys.exit(0)

    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    is_blocked, should_ask, reason = check_command(command, config)

    if is_blocked:
        emit_damage_event(
            tool="Bash", decision="blocked", reason=reason,
            target=command, session_id=session_id,
        )
        print(f"SECURITY: {reason}", file=sys.stderr)
        print(f"Command: {command[:100]}{'...' if len(command) > 100 else ''}", file=sys.stderr)
        sys.exit(2)
    elif should_ask:
        emit_damage_event(
            tool="Bash", decision="asked", reason=reason,
            target=command, session_id=session_id,
        )
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            }
        }
        print(json.dumps(output))
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
