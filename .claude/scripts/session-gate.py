#!/usr/bin/env python3
"""
Raven Enterprise — Session Gate (Stop)
Fires at session end (alongside stream-signal.py).
Checks for any uncommitted secrets or violation flags that need
attention before the session closes.

Outputs a systemMessage if there are open items.
Never blocks — advisory only.
"""

import hashlib, json, sys
from pathlib import Path

CACHE_DIR      = Path(".raven/.cache")
VIOLATION_LOG  = CACHE_DIR / "violations.json"
SECRETS_PATH   = Path(".raven/manifest.secrets.json")


def clear_skill_reminder_flag():
    """Remove the per-session skill reminder flag so next session fires fresh."""
    try:
        h = hashlib.md5(str(Path.cwd().resolve()).encode()).hexdigest()[:8]
        flag = Path(f"/tmp/raven_skill_{h}.flag")
        flag.unlink(missing_ok=True)
    except Exception:
        pass


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text()) if path.exists() else (default or {})
    except Exception:
        return default or {}


def main():
    try:
        json.loads(sys.stdin.read())
    except Exception:
        pass

    clear_skill_reminder_flag()

    warnings = []

    # Check for unresolved violations
    violations = load_json(VIOLATION_LOG, {"items": []})
    unresolved = [v for v in violations.get("items", []) if not v.get("resolved")]
    if len(unresolved) > 1:
        warnings.append(f"{len(unresolved)} unresolved guard violations this session")

    # Check for secrets-in-code patterns (flagged by secret-scan.py)
    scan_flags = load_json(CACHE_DIR / "secret-scan-flags.json", {"flags": []})
    if scan_flags.get("flags"):
        warnings.append("⚠️  Possible secrets detected in written files — review before committing")

    if warnings:
        msg = "Raven session end:\n" + "\n".join(f"  • {w}" for w in warnings)
        print(json.dumps({"systemMessage": msg}))

    sys.exit(0)


if __name__ == "__main__":
    main()
