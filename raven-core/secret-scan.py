#!/usr/bin/env python3
# Raven — Secret Scanner v2.1
# Modes:
#   pre-commit (default) — scans staged files via git diff --cached
#   --pr                 — scans PR diff between base and head (CI mode)
#   --file <path>        — scans a single file directly
# Exit 1 = hard block.

import sys, os, re, subprocess, argparse, json
from pathlib import Path
_PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))).resolve()

# Windows' default console/pipe encoding (cp1252) can't encode the emoji used
# in this script's own output -- crashing what's designed to be advisory/
# fail-open output into a hard crash. errors="replace" guarantees this can
# never crash on any platform; worst case an emoji renders as a placeholder.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

parser = argparse.ArgumentParser(description="Raven Secret Scanner")
parser.add_argument("--pr",                action="store_true", help="PR mode — scan diff vs base branch")
parser.add_argument("--changed-files-only",action="store_true", help="Only scan files changed in PR")
parser.add_argument("--file",              default=None,        help="Scan a single file")
parser.add_argument("--base-ref",          default=None,        help="Base branch ref for PR diff")
args = parser.parse_args()

PR_MODE = args.pr or args.changed_files_only

# When invoked as a PostToolUse hook (no --file, no --pr), read file path from
# the hook JSON payload on stdin instead of requiring jq shell substitution.
if not args.file and not PR_MODE and not sys.stdin.isatty():
    try:
        payload = json.loads(sys.stdin.read())
        _fp = (payload.get("tool_input") or {}).get("file_path") or \
              (payload.get("tool_response") or {}).get("filePath")
        if _fp:
            args.file = _fp
    except Exception:
        pass

# ── Secret patterns ────────────────────────────────────────────────────────────
PATTERNS = [
    (r'AKIA[0-9A-Z]{16}',                                                    "AWS Access Key"),
    (r'(?i)aws.{0,20}secret.{0,20}["\'][A-Za-z0-9+/]{40}["\']',             "AWS Secret Key"),
    (r'sk-[A-Za-z0-9_-]{20,}',                                               "OpenAI API Key"),
    (r'(?i)(api[_-]?key|api[_-]?secret)\s*=\s*["\'][A-Za-z0-9+/._-]{16,}',  "API Key"),
    (r'(?i)password\s*=\s*["\'][^"\']{8,}["\']',                             "Hardcoded Password"),
    (r'-----BEGIN (RSA|EC|OPENSSH|DSA) PRIVATE KEY-----',                     "Private Key"),
    (r'(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}',                               "Bearer Token"),
    (r'(?i)(secret_key|private_key)\s*=\s*["\'][^"\']{8,}["\']',            "Secret Key"),
    (r'AIza[0-9A-Za-z\-_]{35}',                                              "Google API Key"),
    (r'ghp_[A-Za-z0-9]{36}',                                                 "GitHub Personal Token"),
    (r'xoxb-[0-9]{11}-[0-9]{11}-[A-Za-z0-9]{24}',                          "Slack Bot Token"),
]

# ── Critical .gitignore entries ────────────────────────────────────────────────
REQUIRED_GITIGNORE = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "manifest.secrets.json",
    ".raven/manifest.secrets.json",
]

violations = []
warnings   = []

def staged_files():
    if PR_MODE:
        base = args.base_ref or os.environ.get("GITHUB_BASE_REF", "main")
        try:
            out = subprocess.check_output(
                ["git", "diff", "--name-only", "--diff-filter=ACM", f"origin/{base}...HEAD"]
            ).decode().split()
            return out
        except:
            return []
    if args.file:
        return [args.file]
    out = subprocess.check_output(
        ["git","diff","--cached","--name-only","--diff-filter=ACM"]
    ).decode().split()
    return out

def file_content(path):
    if args.file:
        try:
            return open(path).read()
        except:
            return ""
    if PR_MODE:
        try:
            return open(path).read()
        except:
            return ""
    try:
        return subprocess.check_output(["git","show",f":{path}"]).decode(errors="ignore")
    except:
        return ""

# ── Check 1: .gitignore exists (pre-commit / PR mode only — not hook mode) ─────
_gitignore = _PROJECT / ".gitignore"
if not args.file and not _gitignore.exists():
    violations.append(
        "No .gitignore yet — without one, it's easy to commit secrets or junk by accident.\n"
        "     What to do: create a starter with —\n"
        "     curl -fsSL https://www.gitignore.io/api/python,node,macos > .gitignore"
    )
else:
    gitignore_content = _gitignore.read_text(encoding="utf-8", errors="ignore") if _gitignore.exists() else ""

    # ── Check 2: .gitignore covers critical entries (pre-commit / PR mode) ────
    if not args.file:
        for entry in REQUIRED_GITIGNORE:
            base = entry.replace("*","").replace(".","").strip("/")
            if entry not in gitignore_content and base not in gitignore_content:
                warnings.append(f".gitignore doesn't cover '{entry}' yet — consider adding it")

# ── Check 3: .env file exists but not gitignored ──────────────────────────────
for env_file in [".env", ".env.local", ".env.production", ".env.staging"]:
    if (_PROJECT / env_file).exists():
        gitignore_ok = _gitignore.exists() and (
            env_file in gitignore_content or
            ".env" in gitignore_content
        )
        if not gitignore_ok:
            violations.append(
                f"{env_file} exists but isn't in .gitignore — it could get committed by accident.\n"
                f"     Why this matters: .env files usually hold keys and passwords.\n"
                f"     What to do:  echo '{env_file}' >> .gitignore"
            )

# ── Check 4: manifest.secrets.json not staged ─────────────────────────────────
files = staged_files()
if ".raven/manifest.secrets.json" in files or "manifest.secrets.json" in files:
    violations.append(
        "manifest.secrets.json is staged — this file holds your SMTP/Slack credentials "
        "and must never be committed.\n"
        "     What to do:  git reset HEAD .raven/manifest.secrets.json"
    )

# ── Check 5: Secret patterns in staged files ──────────────────────────────────
for path in files:
    content = file_content(path)
    if not content:
        continue
    for pattern, label in PATTERNS:
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(pattern, line) and not line.strip().startswith("#"):
                violations.append(
                    f"Looks like a {label} on line {i} of {path}.\n"
                    f"     Why this matters: committed secrets get scraped from git history within minutes — "
                    f"rotating a leaked key is far more painful than fixing this now.\n"
                    f"     What to do: move it to an environment variable or .env file (which is gitignored), "
                    f"then unstage this file with:  git reset HEAD {path}"
                )

# ── Check 6: .pem / .key files staged ─────────────────────────────────────────
for path in files:
    if any(path.endswith(ext) for ext in [".pem",".key",".p12",".pfx",".cer"]):
        violations.append(
            f"{path} looks like a certificate or private key — these should never be committed.\n"
            f"     What to do: store it outside the repo (or in a secrets manager), then:  "
            f"git reset HEAD {path}"
        )

# ── Output ─────────────────────────────────────────────────────────────────────
if warnings:
    print("\n💡 Raven noticed a few things worth tidying up (not blocking):")
    for w in warnings:
        print(f"  • {w}")

if violations:
    print("\n🛡️  Raven stopped this commit to protect you — here's what to fix:\n")
    for v in violations:
        print(f"  • {v}\n")

    # In hook mode (--file): write a flag so session-gate.py can warn at session end,
    # non-blocking. In pre-commit mode: hard block (exit 1) without writing the flag
    # (git handles it) -- a real commit is worth stopping, a PostToolUse edit isn't.
    if args.file:
        try:
            from datetime import datetime as _dt, timezone as _tz
            _cache = _PROJECT / ".raven" / ".cache"
            _cache.mkdir(parents=True, exist_ok=True)
            _flag_path = _cache / "secret-scan-flags.json"
            _existing: list = []
            if _flag_path.exists():
                try:
                    _existing = json.loads(_flag_path.read_text(encoding="utf-8-sig")).get("flags", [])
                except Exception:
                    _existing = []
            _existing.append({
                "file":       args.file,
                "violations": violations,
                "ts":         _dt.now(_tz.utc).isoformat(),
            })
            _flag_path.write_text(json.dumps({"flags": _existing}, indent=2))
        except Exception:
            pass  # flag write failure must never block hook execution
    else:
        print("  Once you've fixed the above, just commit again. Nothing else is needed.")
        print("  (If a match is a false positive, say so and we'll tune the pattern.)\n")
        sys.exit(1)

if not warnings and not violations:
    print("✅ Secret scan passed — no secrets in your staged files. Safe to commit.")

sys.exit(0)
