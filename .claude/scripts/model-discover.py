#!/usr/bin/env python3
"""
Raven Enterprise — Model Discovery
Know → Find → Ask → Write

Discovers available models across all providers and writes .model.env.
Runs at raven init. Never stores credentials — only capability declarations.

Providers checked:
  Anthropic   (ANTHROPIC_API_KEY env)
  OpenAI      (OPENAI_API_KEY env)
  Groq        (GROQ_API_KEY env)
  Gemini      (GEMINI_API_KEY / GOOGLE_API_KEY env)
  Ollama      (localhost:11434 — no key needed)
  LM Studio   (localhost:1234 — no key needed)
  Together.ai (TOGETHER_API_KEY env)
"""

import json, os, subprocess, sys, urllib.request, urllib.error
from pathlib import Path

MODEL_ENV_PATH = Path(".model.env")

PROVIDERS = {
    "anthropic": {
        "env_key":   "ANTHROPIC_API_KEY",
        "models":    ["claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-5"],
        "cost_tier": {"claude-haiku-4-5": "low", "claude-sonnet-4-5": "medium", "claude-opus-4-5": "high"},
        "check":     "env",
    },
    "openai": {
        "env_key":   "OPENAI_API_KEY",
        "models":    ["gpt-4o-mini", "gpt-4o", "o3-mini"],
        "cost_tier": {"gpt-4o-mini": "low", "gpt-4o": "medium", "o3-mini": "medium"},
        "check":     "env",
    },
    "groq": {
        "env_key":   "GROQ_API_KEY",
        "models":    ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
        "cost_tier": {"llama-3.1-8b-instant": "low", "llama-3.3-70b-versatile": "low", "mixtral-8x7b-32768": "low"},
        "check":     "env",
    },
    "gemini": {
        "env_key":   "GEMINI_API_KEY",
        "env_alt":   "GOOGLE_API_KEY",
        "models":    ["gemini-2.0-flash", "gemini-1.5-pro"],
        "cost_tier": {"gemini-2.0-flash": "low", "gemini-1.5-pro": "medium"},
        "check":     "env",
    },
    "ollama": {
        "endpoint":  "http://localhost:11434/api/tags",
        "models":    [],   # discovered dynamically
        "cost_tier": {},   # all free
        "check":     "local",
    },
    "lmstudio": {
        "endpoint":  "http://localhost:1234/v1/models",
        "models":    [],
        "cost_tier": {},
        "check":     "local",
    },
    "together": {
        "env_key":   "TOGETHER_API_KEY",
        "models":    ["meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo", "mistralai/Mixtral-8x7B-Instruct-v0.1"],
        "cost_tier": {"meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": "low", "mistralai/Mixtral-8x7B-Instruct-v0.1": "low"},
        "check":     "env",
    },
}

# ── Discovery ─────────────────────────────────────────────────────────────────

def check_env_provider(name: str, config: dict) -> dict | None:
    key = os.environ.get(config.get("env_key", "")) or os.environ.get(config.get("env_alt", ""))
    if not key:
        return None
    return {
        "provider":  name,
        "available": True,
        "models":    config["models"],
        "cost_tier": config["cost_tier"],
        "key_var":   config.get("env_key", ""),
    }

def check_local_provider(name: str, config: dict) -> dict | None:
    try:
        req = urllib.request.Request(config["endpoint"], headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
        models = []
        if name == "ollama":
            models = [m["name"] for m in data.get("models", [])]
        elif name == "lmstudio":
            models = [m["id"] for m in data.get("data", [])]
        if not models:
            return None
        return {
            "provider":  name,
            "available": True,
            "models":    models,
            "cost_tier": {m: "free" for m in models},
            "key_var":   None,
        }
    except Exception:
        return None

def discover_all() -> list[dict]:
    found = []
    for name, config in PROVIDERS.items():
        result = None
        if config["check"] == "env":
            result = check_env_provider(name, config)
        elif config["check"] == "local":
            result = check_local_provider(name, config)
        if result:
            found.append(result)
    return found

# ── Routing table ─────────────────────────────────────────────────────────────

def build_routing_table(providers: list[dict]) -> dict:
    """
    Pick cheapest adequate model per task tier.
    Tiers: local → simple → medium → complex
    """
    free_models   = [(p["provider"], m) for p in providers for m, t in p["cost_tier"].items() if t == "free"]
    low_models    = [(p["provider"], m) for p in providers for m, t in p["cost_tier"].items() if t == "low"]
    medium_models = [(p["provider"], m) for p in providers for m, t in p["cost_tier"].items() if t == "medium"]
    high_models   = [(p["provider"], m) for p in providers for m, t in p["cost_tier"].items() if t == "high"]

    def pick(candidates, fallback=None):
        return candidates[0] if candidates else fallback

    local_pick  = pick(free_models)
    simple_pick = pick(low_models,    local_pick)
    medium_pick = pick(medium_models, simple_pick)
    complex_pick = pick(high_models,  medium_pick)

    def fmt(t):
        return f"{t[0]}/{t[1]}" if t else "anthropic/claude-sonnet-4-5"

    return {
        "LOCAL_ONLY": fmt(local_pick),    # local Ollama/LMStudio — free, private
        "SIMPLE":     fmt(simple_pick),   # grep, rename, boilerplate
        "MEDIUM":     fmt(medium_pick),   # new function, test, review
        "COMPLEX":    fmt(complex_pick),  # architecture, refactor, debug
    }

# ── Write .model.env ──────────────────────────────────────────────────────────

def write_model_env(providers: list[dict], routing: dict):
    lines = [
        "# Raven Enterprise — Model Capabilities",
        "# Auto-generated by model-discover.py — safe to commit (no secrets)",
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
        lines.append(f"available = true")
        if p.get("key_var"):
            lines.append(f"key_var   = {p['key_var']}")
        lines.append(f"models    = {', '.join(p['models'])}")
        for model, tier in p["cost_tier"].items():
            lines.append(f"tier.{model} = {tier}")
        lines.append("")

    MODEL_ENV_PATH.write_text("\n".join(lines))

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("🔍 Raven — Discovering available models...\n")

    providers = discover_all()

    if not providers:
        print("⚠️  No model providers detected.")
        print("   Set ANTHROPIC_API_KEY, GROQ_API_KEY, or start Ollama and re-run.")
        print("   Raven will use Claude (current session model) as fallback.\n")
        return

    print(f"✅ Found {len(providers)} provider(s):\n")
    for p in providers:
        print(f"   {p['provider']:12} → {len(p['models'])} model(s): {', '.join(p['models'][:3])}")
        if len(p["models"]) > 3:
            print(f"{'':16}   + {len(p['models'])-3} more")

    routing = build_routing_table(providers)
    print(f"\n📋 Routing table:")
    print(f"   LOCAL_ONLY → {routing['LOCAL_ONLY']}")
    print(f"   SIMPLE     → {routing['SIMPLE']}")
    print(f"   MEDIUM     → {routing['MEDIUM']}")
    print(f"   COMPLEX    → {routing['COMPLEX']}")

    # Ask before writing
    print(f"\n   Write to .model.env? [Y/n] ", end="", flush=True)
    answer = sys.stdin.readline().strip().lower()
    if answer in ("n", "no"):
        print("   Skipped. Run again to write.")
        return

    write_model_env(providers, routing)

    # Ensure .model.env is gitignored
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text()
        if ".model.env" not in content:
            gitignore.write_text(content + "\n.model.env\n")
            print("   ✅ .model.env added to .gitignore")

    print(f"\n✅ .model.env written. Raven will route tasks to cheapest adequate model.")
    print(f"   Edit .model.env at any time to override routing decisions.\n")

if __name__ == "__main__":
    main()
