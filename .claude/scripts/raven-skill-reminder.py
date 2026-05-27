#!/usr/bin/env python3
"""
Raven — UserPromptSubmit Hook
Fires before every model response on brownfield/Raven projects.
Injects a skill trigger on the FIRST message only — silent thereafter.
Session flag: /tmp/raven_skill_{cwd_hash}.flag (cleared by session-gate at Stop)

Token cost: ~10 tok on message 1, 0 tok on all subsequent messages.
"""

import hashlib, json, sys
from pathlib import Path

# Domain → skill map (same order / logic as session-start.py)
DOMAIN_SKILL_MAP = [
    {
        "name":          "Salesforce",
        "skill":         "raven:salesforce-specialist",
        "markers":       ["sfdx-project.json", ".forceignore"],
        "dirs":          ["force-app"],
        "globs":         [],
        "keyword_files": [],
        "keyword":       "",
    },
    {
        "name":          "Odoo",
        "skill":         "raven:odoo-specialist",
        "markers":       ["odoo.conf", ".odoo_upgrade.json"],
        "dirs":          [],
        "globs":         ["**/__manifest__.py"],
        "keyword_files": [],
        "keyword":       "",
    },
    {
        "name":          "Terraform",
        "skill":         "raven:terraform-specialist",
        "markers":       [],
        "dirs":          [],
        "globs":         ["*.tf"],
        "keyword_files": [],
        "keyword":       "",
    },
    {
        "name":          "Kubernetes",
        "skill":         "raven:k8s-specialist",
        "markers":       [],
        "dirs":          ["k8s", "kubernetes", "helm", "charts"],
        "globs":         [],
        "keyword_files": [],
        "keyword":       "",
    },
    {
        "name":          "Kafka",
        "skill":         "raven:kafka-specialist",
        "markers":       [],
        "dirs":          [],
        "globs":         [],
        "keyword_files": ["requirements.txt", "docker-compose.yml", "pyproject.toml"],
        "keyword":       "kafka",
    },
    {
        "name":          "Oracle",
        "skill":         "raven:oracle-db-specialist",
        "markers":       [],
        "dirs":          [],
        "globs":         ["*.pkb", "*.pks"],
        "keyword_files": ["requirements.txt"],
        "keyword":       "cx_Oracle",
    },
    {
        "name":          "AWS",
        "skill":         "raven:aws-specialist",
        "markers":       ["cdk.json", "serverless.yml", "serverless.yaml", "sam.yaml"],
        "dirs":          [],
        "globs":         [],
        "keyword_files": [],
        "keyword":       "",
    },
    {
        "name":          "FastAPI",
        "skill":         "raven:fastapi-specialist",
        "markers":       [],
        "dirs":          [],
        "globs":         [],
        "keyword_files": ["requirements.txt", "pyproject.toml"],
        "keyword":       "fastapi",
    },
]


def detect_domain(cwd: Path):
    """Returns (skill, name) or (None, None). Fast — no heavy recursion."""
    for entry in DOMAIN_SKILL_MAP:
        for marker in entry["markers"]:
            if (cwd / marker).exists():
                return entry["skill"], entry["name"]
        for d in entry["dirs"]:
            if (cwd / d).is_dir():
                return entry["skill"], entry["name"]
        # Globs — use non-recursive first, then single-level recursive
        for pattern in entry["globs"]:
            try:
                found = next(iter(cwd.glob(pattern)), None)
                if found:
                    return entry["skill"], entry["name"]
            except Exception:
                pass
        keyword = entry["keyword"]
        if keyword:
            for kf in entry["keyword_files"]:
                kf_path = cwd / kf
                if kf_path.exists():
                    try:
                        if keyword.lower() in kf_path.read_text(errors="ignore").lower():
                            return entry["skill"], entry["name"]
                    except Exception:
                        pass
    return None, None


def is_raven_project(cwd: Path) -> bool:
    if (cwd / ".raven" / "manifest.json").exists():
        return True
    if (cwd / ".model.env").exists():
        return True
    return False


def get_flag_path(cwd: Path) -> Path:
    """Per-project session flag in /tmp — cleared by session-gate at Stop."""
    h = hashlib.md5(str(cwd.resolve()).encode()).hexdigest()[:8]
    return Path(f"/tmp/raven_skill_{h}.flag")


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    cwd = Path.cwd()

    if not is_raven_project(cwd):
        sys.exit(0)

    flag = get_flag_path(cwd)

    # After first message: silent — skill is already in context
    if flag.exists():
        sys.exit(0)

    # First message: inject reminder + set flag
    skill, domain_name = detect_domain(cwd)
    if skill:
        context = f"Raven: invoke {skill} before coding."
    else:
        context = "Raven guards active — load domain skill before coding."

    flag.touch()

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName":    "UserPromptSubmit",
            "additionalContext": context,
        }
    }))


if __name__ == "__main__":
    main()
