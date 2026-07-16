#!/usr/bin/env python3
"""
Raven — SessionStart Hook
Auto-discovers models, classifies project as brownfield or greenfield,
and injects context into the session before the user types anything.

Outputs JSON with additionalContext — consumed by Claude Code SessionStart hook.
Never prompts interactively. Never reads .env or credential files.
"""

import json, os, subprocess, sys, urllib.request, urllib.error
from datetime import datetime, timezone, date
from pathlib import Path

_PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))).resolve()

# Windows: reconfigure stdout/stderr to UTF-8 so emoji in print() don't crash
for _stream in (sys.stdout, sys.stderr):
    try:
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Domain → Skill Map ────────────────────────────────────────────────────────
# Maps detected project domain to the Raven specialist skill to invoke.
# Order matters — first match wins.

DOMAIN_SKILL_MAP = [
    # Salesforce — unambiguous marker files
    {
        "name":    "Salesforce",
        "skill":   "raven:salesforce-specialist",
        "markers": ["sfdx-project.json", ".forceignore"],
        "dirs":    ["force-app"],
        "globs":   [],
    },
    # Odoo — __manifest__.py is the canonical Odoo module marker
    {
        "name":    "Odoo",
        "skill":   "raven:odoo-specialist",
        "markers": ["odoo.conf", ".odoo_upgrade.json"],
        "dirs":    [],
        "globs":   ["**/__manifest__.py"],  # checked with limit
    },
    # Terraform
    {
        "name":    "Terraform",
        "skill":   "raven:terraform-specialist",
        "markers": [],
        "dirs":    [],
        "globs":   ["*.tf", "**/*.tf"],
    },
    # Kubernetes / Helm
    {
        "name":    "Kubernetes",
        "skill":   "raven:k8s-specialist",
        "markers": [],
        "dirs":    ["k8s", "kubernetes", "helm", "charts"],
        "globs":   [],
    },
    # Kafka — check requirements or docker-compose
    {
        "name":    "Kafka",
        "skill":   "raven:kafka-specialist",
        "markers": [],
        "dirs":    [],
        "globs":   [],
        "keyword_files": ["requirements.txt", "docker-compose.yml", "pyproject.toml"],
        "keyword":       "kafka",
    },
    # Oracle — APEX / DB
    {
        "name":    "Oracle",
        "skill":   "raven:oracle-db-specialist",
        "markers": [],
        "dirs":    [],
        "globs":   ["**/*.pkb", "**/*.pks", "**/*.sql"],
        "keyword_files": ["requirements.txt"],
        "keyword":       "cx_Oracle",
    },
    # AWS / Cloud
    {
        "name":    "AWS",
        "skill":   "raven:aws-specialist",
        "markers": ["cdk.json", "serverless.yml", "serverless.yaml", "sam.yaml", "template.yaml"],
        "dirs":    [],
        "globs":   [],
    },
    # FastAPI / Python web
    {
        "name":    "FastAPI",
        "skill":   "raven:fastapi-specialist",
        "markers": [],
        "dirs":    [],
        "globs":   [],
        "keyword_files": ["requirements.txt", "pyproject.toml"],
        "keyword":       "fastapi",
    },
]


def detect_domain(cwd: Path) -> tuple[str | None, str | None]:
    """Detect the project's primary domain. Returns (skill, label) or (None, None)."""
    for entry in DOMAIN_SKILL_MAP:
        # Check marker files
        for marker in entry.get("markers", []):
            if (cwd / marker).exists():
                return entry["skill"], entry["name"]
        # Check marker directories
        for d in entry.get("dirs", []):
            if (cwd / d).is_dir():
                return entry["skill"], entry["name"]
        # Check glob patterns (with a hard limit to stay fast)
        for pattern in entry.get("globs", []):
            try:
                found = next(iter(cwd.glob(pattern)), None)
                if found:
                    return entry["skill"], entry["name"]
            except Exception:
                pass
        # Check keyword in specific files
        keyword = entry.get("keyword", "")
        if keyword:
            for kf in entry.get("keyword_files", []):
                kf_path = cwd / kf
                if kf_path.exists():
                    try:
                        if keyword.lower() in kf_path.read_text(errors="ignore").lower():
                            return entry["skill"], entry["name"]
                    except Exception:
                        pass
    return None, None


# ── Brownfield / Greenfield Detection ─────────────────────────────────────────

def detect_project_type() -> dict:
    signals = []
    project_type = "greenfield"
    confidence = "LOW"

    cwd = Path(".")

    # Git history depth
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        commit_count = int(result.stdout.strip()) if result.returncode == 0 else 0
        if commit_count > 50:
            signals.append(f"git: {commit_count} commits")
            project_type = "brownfield"
            confidence = "HIGH"
        elif commit_count > 5:
            signals.append(f"git: {commit_count} commits")
            project_type = "brownfield"
            confidence = "MEDIUM"
        elif commit_count > 0:
            signals.append(f"git: {commit_count} commits (new repo)")
    except Exception:
        signals.append("git: no repo detected")

    # Raven manifest
    if (cwd / ".raven" / "manifest.json").exists():
        signals.append("raven: manifest present")
        project_type = "brownfield"
        confidence = "HIGH"

    # Language / framework signals
    lang_signals = {
        "package.json":      "Node.js",
        "requirements.txt":  "Python",
        "pyproject.toml":    "Python",
        "Cargo.toml":        "Rust",
        "go.mod":            "Go",
        "pom.xml":           "Java/Maven",
        "build.gradle":      "Java/Gradle",
        "Gemfile":           "Ruby",
        "composer.json":     "PHP",
        "pubspec.yaml":      "Dart/Flutter",
    }
    detected_langs = []
    for file, lang in lang_signals.items():
        if (cwd / file).exists():
            detected_langs.append(lang)

    if detected_langs:
        signals.append(f"stack: {', '.join(detected_langs[:3])}")
        if project_type == "greenfield":
            project_type = "brownfield"
            confidence = "MEDIUM"

    # File count (rough proxy for existing codebase) — git ls-files is fast on any repo size
    try:
        src_extensions = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".cs"}
        ls = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, timeout=5
        )
        if ls.returncode == 0:
            src_files = [f for f in ls.stdout.splitlines() if Path(f).suffix in src_extensions]
        else:
            src_files = []
        file_count = len(src_files)
        if file_count > 100:
            signals.append(f"codebase: {file_count} source files")
            project_type = "brownfield"
            confidence = "HIGH"
        elif file_count > 10:
            signals.append(f"codebase: {file_count} source files")
        elif file_count > 0:
            signals.append(f"codebase: {file_count} source file(s)")
    except Exception:
        pass

    # Infrastructure signals
    infra_signals = {
        "terraform": "Terraform",
        ".github/workflows": "GitHub Actions",
        "Dockerfile": "Docker",
        "docker-compose.yml": "Docker Compose",
        "kubernetes": "Kubernetes",
        "helm": "Helm",
    }
    detected_infra = []
    for path, label in infra_signals.items():
        if (cwd / path).exists():
            detected_infra.append(label)
    if detected_infra:
        signals.append(f"infra: {', '.join(detected_infra[:3])}")

    return {
        "type":       project_type,
        "confidence": confidence,
        "signals":    signals,
        "langs":      detected_langs,
    }


# ── Model Discovery ────────────────────────────────────────────────────────────

CLOUD_PROVIDERS = {
    "anthropic": {
        "env_keys": ["ANTHROPIC_API_KEY"],
        "models":   ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"],
        "tiers":    {"claude-haiku-4-5-20251001": "low", "claude-sonnet-4-6": "medium", "claude-opus-4-8": "high"},
    },
    "openai": {
        "env_keys": ["OPENAI_API_KEY"],
        "models":   ["gpt-4o-mini", "gpt-4o", "o3-mini"],
        "tiers":    {"gpt-4o-mini": "low", "gpt-4o": "medium", "o3-mini": "medium"},
    },
    "groq": {
        "env_keys": ["GROQ_API_KEY"],
        "models":   ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"],
        "tiers":    {"llama-3.1-8b-instant": "low", "llama-3.3-70b-versatile": "low"},
    },
    "gemini": {
        "env_keys": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "models":   ["gemini-2.0-flash", "gemini-1.5-pro"],
        "tiers":    {"gemini-2.0-flash": "low", "gemini-1.5-pro": "medium"},
    },
    "together": {
        "env_keys": ["TOGETHER_API_KEY"],
        "models":   ["meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"],
        "tiers":    {"meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": "low"},
    },
}

LOCAL_PROVIDERS = {
    "ollama":   "http://localhost:11434/api/tags",
    "lmstudio": "http://localhost:1234/v1/models",
}


def discover_cloud() -> list[dict]:
    found = []
    for name, cfg in CLOUD_PROVIDERS.items():
        key = next((os.environ.get(k) for k in cfg["env_keys"] if os.environ.get(k)), None)
        if key:
            found.append({
                "provider": name,
                "models":   cfg["models"],
                "tiers":    cfg["tiers"],
                "source":   "env",
            })
    return found


def discover_local() -> list[dict]:
    found = []
    for name, endpoint in LOCAL_PROVIDERS.items():
        try:
            req = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
            models = []
            if name == "ollama":
                models = [m["name"] for m in data.get("models", [])]
            elif name == "lmstudio":
                models = [m["id"] for m in data.get("data", [])]
            if models:
                found.append({
                    "provider": name,
                    "models":   models,
                    "tiers":    {m: "free" for m in models},
                    "source":   "local",
                })
        except Exception:
            pass
    return found


def build_routing(providers: list[dict]) -> dict:
    free    = [(p["provider"], m) for p in providers for m, t in p["tiers"].items() if t == "free"]
    low     = [(p["provider"], m) for p in providers for m, t in p["tiers"].items() if t == "low"]
    medium  = [(p["provider"], m) for p in providers for m, t in p["tiers"].items() if t == "medium"]
    high    = [(p["provider"], m) for p in providers for m, t in p["tiers"].items() if t == "high"]

    def pick(lst, fallback=None):
        return lst[0] if lst else fallback

    local_pick   = pick(free)
    simple_pick  = pick(low,    local_pick)
    medium_pick  = pick(medium, simple_pick)
    complex_pick = pick(high,   medium_pick)

    def fmt(t): return f"{t[0]}/{t[1]}" if t else "anthropic/claude-sonnet-4-5"

    return {
        "LOCAL_ONLY": fmt(local_pick),
        "SIMPLE":     fmt(simple_pick),
        "MEDIUM":     fmt(medium_pick),
        "COMPLEX":    fmt(complex_pick),
    }


def write_model_env(providers: list[dict], routing: dict):
    model_env = _PROJECT / ".model.env"
    lines = [
        "# Raven — Model Capabilities",
        "# Auto-generated by session-start.py — safe to commit (no secrets)",
        "# Edit manually to override routing decisions",
        "",
        "[routing]",
        f"LOCAL_ONLY = {routing['LOCAL_ONLY']}",
        f"SIMPLE     = {routing['SIMPLE']}",
        f"MEDIUM     = {routing['MEDIUM']}",
        f"COMPLEX    = {routing['COMPLEX']}",
        "",
    ]
    for p in providers:
        lines.append(f"[{p['provider']}]")
        lines.append("available = true")
        lines.append(f"source    = {p['source']}")
        lines.append(f"models    = {', '.join(p['models'][:5])}")
        for model, tier in list(p["tiers"].items())[:5]:
            lines.append(f"tier.{model} = {tier}")
        lines.append("")

    model_env.write_text("\n".join(lines))

    # Ensure gitignored
    gitignore = _PROJECT / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".model.env" not in content:
            gitignore.write_text(content.rstrip() + "\n.model.env\n")


# ── Format output ──────────────────────────────────────────────────────────────

def format_context(project: dict, providers: list[dict], routing: dict, model_env_written: bool, domain_skill: tuple = (None, None)) -> str:
    lines = []

    # Project classification
    badge = "🟤 BROWNFIELD" if project["type"] == "brownfield" else "🟢 GREENFIELD"
    lines.append(f"{badge}  [{project['confidence']} confidence]")
    if project["signals"]:
        lines.append("  Signals: " + " · ".join(project["signals"]))

    lines.append("")

    # Model landscape
    if providers:
        local_p  = [p for p in providers if p["source"] == "local"]
        cloud_p  = [p for p in providers if p["source"] == "env"]

        if local_p:
            lines.append(f"⚡ LOCAL: " + ", ".join(
                f"{p['provider']} ({len(p['models'])} model{'s' if len(p['models'])!=1 else ''})"
                for p in local_p
            ))
        if cloud_p:
            lines.append(f"☁️  CLOUD: " + ", ".join(p["provider"] for p in cloud_p))

        lines.append("")
        lines.append("Model routing:")
        lines.append(f"  LOCAL_ONLY → {routing['LOCAL_ONLY']}")
        lines.append(f"  SIMPLE     → {routing['SIMPLE']}  (typo fix, rename, simple Q)")
        lines.append(f"  MEDIUM     → {routing['MEDIUM']}  (tests, debugging, docs)")
        lines.append(f"  COMPLEX    → {routing['COMPLEX']}  (architecture, security, multi-file)")

        if model_env_written:
            lines.append("  .model.env written ✓")

        # ── 💰 Cost meter — show prior session spend if available ──────────────
        try:
            session_file = _PROJECT / ".raven" / ".model-session.json"
            if session_file.exists():
                session_data = json.loads(session_file.read_text())
                tok = session_data.get("session_tokens", 0)
                cost = session_data.get("session_cost_usd", 0.0)
                tier_breakdown = session_data.get("tier_counts", {})
                if tok > 0:
                    lines.append("")
                    lines.append(f"💰 Last session: ~{tok:,} tok · ~${cost:.3f}")
                    if tier_breakdown:
                        breakdown = " · ".join(f"{k}:{v}" for k, v in tier_breakdown.items() if v > 0)
                        lines.append(f"   Tiers used: {breakdown}")
        except Exception:
            pass  # Cost meter is best-effort, never blocks session start
    else:
        lines.append("☁️  No additional model providers detected.")
        lines.append("   Claude (current session) is your active model.")
        lines.append("   To add: set ANTHROPIC_API_KEY, GROQ_API_KEY, or start Ollama.")

    # Brownfield advisory + domain skill trigger
    cwd = _PROJECT
    has_manifest  = (cwd / ".raven" / "manifest.json").exists()
    has_claude_md = (cwd / ".claude" / "CLAUDE.md").exists() or (cwd / "CLAUDE.md").exists()

    # ── MANDATORY GREETING — fires for BOTH greenfield and brownfield ──────────
    # First message after install ALWAYS shows the Welcome greeting before any routing.
    # This is hook-enforced, not description-based. Claude cannot skip.
    lines.append("")
    lines.append("━━━ [GREETING REQUIRED] — MANDATORY FIRST RESPONSE ━━━")
    lines.append("On the FIRST user message of this session, Claude MUST respond")
    lines.append("with the EXACT greeting below — no other text, no analysis, no routing yet:")
    lines.append("")
    lines.append('    "Welcome to Raven — your Enterprise Discipline for AI-based Vibe Coding.')
    lines.append("")
    lines.append('     Do you want me to tell you what I can do, or just say — Let\'s Go!"')
    lines.append("")
    lines.append("After user responds:")
    lines.append("  ├─ If user asks 'what can you do' / curious / capabilities:")
    lines.append("  │     → Brief 50-word capability summary covering:")
    lines.append("  │       Andie (planning) · Andie-jr (debug) · 60+ specialists ·")
    lines.append("  │       cost-aware routing · CVE + secret guards · Obsidian memory.")
    lines.append("  │     → End with: 'Ready? Say Let\\'s Go.'")
    lines.append("  │")
    lines.append("  └─ If user says 'Let\\'s Go' / 'go' / states a task:")
    if not has_manifest:
        lines.append("       → GREENFIELD path: AUTO-INVOKE `andie` skill.")
        lines.append("         Andie's Branch A onboarding fires with this exact greeting:")
        lines.append("           '👋 Hey, I\\'m Andie. I\\'m the mind of your installed Raven.")
        lines.append("            Good — you have a keen ask for responsible and resilient AI.")
        lines.append("            I noticed you don\\'t have a manifest yet — to get Raven working,")
        lines.append("            I need to scan your project and build one. OK to proceed?'")
        lines.append("         On YES → Andie scans, asks ≤2 questions, hands off to raven-init.")
    else:
        lines.append("       → BROWNFIELD path: manifest.json ✅ present. Load it, trust stack.")
        lines.append("         Then route by prompt class:")
        lines.append("           [symptom]      → triage-router → andie-jr")
        lines.append("           [architecture] → architect-router → andie")
        skill, domain_label = domain_skill
        if skill:
            lines.append(f"           [domain task]  → {skill} ({domain_label})")
        else:
            lines.append("           [domain task]  → matching specialist (see manifest.stack)")
    lines.append("")
    lines.append("DO NOT skip the greeting. DO NOT route before greeting. DO NOT give")
    lines.append("install instructions — Raven IS installed.")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    # ── Brownfield-specific advisory (after greeting context) ─────────────────
    if project["type"] == "brownfield":
        lines.append("📋 Existing project — Raven IS installed and active.")
        if project["langs"]:
            lines.append(f"   Stack: {', '.join(project['langs'])}")
        skill, domain_label = domain_skill
        if skill:
            lines.append("")
            lines.append(f"⚡ DOMAIN DETECTED: {domain_label}")
            lines.append(f"   After greeting + Let's Go: invoke `{skill}` for domain tasks.")
    else:
        lines.append("🚀 New project — manifest will be created via Andie's Branch A on Let's Go.")

    return "\n".join(lines)


# ── Signal Queue Heartbeat ────────────────────────────────────────────────────

def queue_session_start_event(cwd: Path) -> None:
    """
    Write a session_start event to the signal queue so stream-signal.py always
    has data to send to Hub — even for sessions with no MCP calls or token
    checkpoints.  Only queues when Hub is configured in the manifest.
    """
    manifest_path = cwd / ".raven" / "manifest.json"
    if not manifest_path.exists():
        return  # Not a Raven-managed project

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return

    if not manifest.get("hub_url"):
        return  # No Hub configured — skip

    cache_dir    = cwd / ".raven" / ".cache"
    signal_queue = cache_dir / "signal-queue.json"

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        queue: list = []
        if signal_queue.exists():
            try:
                queue = json.loads(signal_queue.read_text(encoding="utf-8-sig"))
                if not isinstance(queue, list):
                    queue = []
            except Exception:
                queue = []

        queue.append({
            "event_type": "session_start",
            "ts":         datetime.now(timezone.utc).isoformat(),
        })
        signal_queue.write_text(json.dumps(queue, indent=2))
    except Exception:
        pass  # Non-critical — session continues regardless


# ── Auto Project Init ──────────────────────────────────────────────────────────

def auto_init_project(cwd: Path) -> str | None:
    """
    If the current project has no .raven/manifest.json but the global
    raven-config.json exists, create the manifest automatically.

    Returns a status string for the session context, or None if already
    initialised or global config not found.
    """
    raven_dir       = cwd / ".raven"
    manifest        = raven_dir / "manifest.json"
    secrets         = raven_dir / "manifest.secrets.json"
    cache_dir       = raven_dir / ".cache"
    manifest_existed = manifest.exists()

    # Already initialised and complete — nothing to do
    if manifest_existed:
        try:
            existing = json.loads(manifest.read_text(encoding="utf-8-sig"))
            # If key fields are already populated, skip
            if existing.get("hub_url") and existing.get("user_email") and existing.get("org"):
                return None
            # Incomplete manifest — fall through to update it from saved config
        except Exception:
            return None  # Unreadable manifest — leave it alone

    # Global config written by install-windows.ps1
    config_path = Path.home() / ".claude" / "raven-config.json"
    if not config_path.exists():
        return None  # Install script hasn't run yet

    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None

    hub_url   = cfg.get("hub_url", "")
    org       = cfg.get("org", "")
    hub_token = cfg.get("hub_token", "")
    dev_email = cfg.get("dev_email", "")

    if not (hub_url and org and hub_token and dev_email):
        return None  # Config incomplete — skip silently

    project_name = cwd.resolve().name
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Create directories (wrapped — permission errors must not crash the hook)
    try:
        raven_dir.mkdir(exist_ok=True)
        cache_dir.mkdir(exist_ok=True)
    except Exception:
        return None

    # Write manifest.json
    manifest_data = {
        "project":      project_name,
        "org":          org,
        "owner":        dev_email,
        "user_email":   dev_email,
        "hub_url":      hub_url,
        "version":      "1.0.0",
        "raven_version": "3.0.0",
        "stack": {
            "language": [], "frontend": [], "data": [],
            "db": [], "infra": [], "cloud": "none", "libraries": []
        },
        "standards": "raven-v1",
        "guard": {"enabled": True, "version": "1.0"},
        "changelog": [{
            "version":    "1.0.0",
            "date":       now,
            "changed_by": dev_email,
            "summary":    "Raven project auto-initialised by session-start.py",
        }],
    }
    try:
        manifest.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    except Exception:
        return None

    # Write manifest.secrets.json
    secrets_data = {
        "_source":    "session-start-auto-init",
        "_written_at": now,
        "_note":      "Never commit this file. It is listed in .gitignore.",
        "org":        org,
        "hub_url":    hub_url,
        "hub_token":  hub_token,
    }
    try:
        secrets.write_text(json.dumps(secrets_data, indent=2), encoding="utf-8")
    except Exception:
        pass  # secrets file failure is non-fatal

    # Update .gitignore
    gitignore = cwd / ".gitignore"
    ignore_block = (
        "\n# Raven Enterprise -- never commit these"
        "\n.raven/manifest.secrets.json"
        "\n.raven/.cache/"
        "\n.model.env"
        "\n"
    )
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8", errors="ignore")
        if "manifest.secrets.json" not in existing:
            gitignore.write_text(existing.rstrip() + ignore_block, encoding="utf-8")
    else:
        gitignore.write_text(ignore_block.lstrip(), encoding="utf-8")

    action = "updated" if manifest_existed else "created"
    return f"Raven auto-init: {action} .raven/manifest.json for project '{project_name}' (org: {org})"


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # SessionStart hook — read stdin (may be empty or contain session info)
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        hook_input = {}

    # 0. Auto-init project manifest if missing (uses ~\.claude\raven-config.json)
    auto_init_msg = auto_init_project(_PROJECT)

    # 0a. Queue a session_start heartbeat so stream-signal.py always sends to Hub
    queue_session_start_event(_PROJECT)

    # 1. Detect project type
    project = detect_project_type()

    # 2. Detect domain → skill mapping
    domain_skill = detect_domain(_PROJECT)

    # 3. Discover models
    local_providers = discover_local()
    cloud_providers = discover_cloud()
    all_providers   = local_providers + cloud_providers

    # 4. Build routing table
    routing = build_routing(all_providers)

    # 5. Write .model.env if missing or if local providers newly found
    model_env = _PROJECT / ".model.env"
    model_env_written = False
    if not model_env.exists() and all_providers:
        try:
            write_model_env(all_providers, routing)
            model_env_written = True
        except Exception:
            pass  # Non-critical — session continues regardless

    # 6. Format context string
    context = format_context(project, all_providers, routing, model_env_written, domain_skill)
    if auto_init_msg:
        context = auto_init_msg + "\n\n" + context

    # 7. Build compact system notification (always shown in Claude Code UI)
    badge_short = "BROWNFIELD" if project["type"] == "brownfield" else "GREENFIELD"
    skill, domain_label = domain_skill
    skill_line = f" · {domain_label} → {skill}" if skill else ""
    lang_short = ", ".join(project["langs"][:2]) if project["langs"] else ""
    stack_line = f" · {lang_short}" if lang_short else ""

    providers_short = ""
    local_p = [p for p in all_providers if p["source"] == "local"]
    cloud_p = [p for p in all_providers if p["source"] == "env"]
    if local_p:
        providers_short += " · " + ", ".join(f"{p['provider']}" for p in local_p)
    if cloud_p:
        providers_short += " · " + ", ".join(p["provider"] for p in cloud_p)

    system_message = f"Raven ✅  {badge_short}{stack_line}{skill_line}{providers_short}"

    # 8. Increment daily session counter for Hub signal accuracy.
    # /clear and /compact also fire SessionStart, but they continue the same
    # logical session — skip them. Anything else (startup, resume, or missing
    # source on older Claude Code clients) counts.
    _source = (hook_input.get("source") or "").lower()
    if _source not in ("clear", "compact"):
        _cache = _PROJECT / ".raven" / ".cache"
        _stats_path = _cache / "session-stats.json"
        _today = date.today().isoformat()
        try:
            _cache.mkdir(parents=True, exist_ok=True)
            _stats = json.loads(_stats_path.read_text()) if _stats_path.exists() else {}
            if _stats.get("date") != _today:
                _stats = {"date": _today, "sessions": 0, "sessions_sent": 0, "cost_sent": 0.0}
            _stats["sessions"] = _stats.get("sessions", 0) + 1
            _stats_path.write_text(json.dumps(_stats))
        except Exception:
            pass

    # 9. Output JSON for SessionStart hook
    output = {
        "systemMessage": system_message,
        "hookSpecificOutput": {
            "hookEventName":   "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
