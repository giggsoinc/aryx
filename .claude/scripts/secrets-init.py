#!/usr/bin/env python3
"""
Raven Enterprise — Secrets Init
Detects secrets from .env, vault, or prompts. Writes manifest.secrets.json.
Never commits secrets. Never blocks solo mode.

Called by: /raven-init skill after manifest.json is written.
Also called standalone: python3 secrets-init.py

Priority:
  1. .env file in project root
  2. Vault CLI (1Password / HashiCorp Vault / Doppler / AWS SM)
  3. Interactive prompt
  4. Solo mode — no secrets, degraded features, never halt
"""

import json, os, sys, subprocess, getpass
from pathlib import Path
from datetime import datetime, timezone

MANIFEST_PATH = Path(".raven/manifest.json")
SECRETS_PATH  = Path(".raven/manifest.secrets.json")
ENV_PATH      = Path(".env")

# Which env var names map to which secret fields
ENV_MAP = {
    # SMTP
    "SMTP_HOST":     "smtp_host",
    "SMTP_PORT":     "smtp_port",
    "SMTP_USER":     "smtp_user",
    "SMTP_USERNAME": "smtp_user",
    "SMTP_PASSWORD": "smtp_password",
    "SMTP_PASS":     "smtp_password",
    "SMTP_FROM":     "smtp_from",
    # Hub
    "RAVEN_HUB_URL": "hub_url",
    "HUB_URL":       "hub_url",
    "RAVEN_HUB_TOKEN": "hub_token",
    "HUB_TOKEN":     "hub_token",
    "HUB_SECRET_KEY": "hub_token",
    # Notifications
    "SLACK_WEBHOOK":      "slack_webhook",
    "HUB_ALERT_WEBHOOK":  "slack_webhook",
    "HUB_ALERT_EMAIL":    "admin_email",
    "RAVEN_ADMIN_EMAIL":  "admin_email",
    # Audit log
    "AUDIT_BUCKET":       "audit_bucket",
    "RAVEN_AUDIT_BUCKET": "audit_bucket",
    "S3_BUCKET":          "audit_bucket",
    # Admin
    "RAVEN_ADMIN_EMAIL":  "admin_email",
    "ADMIN_EMAIL":        "admin_email",
}

def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text()) if path.exists() else (default or {})
    except Exception:
        return default or {}

def parse_env_file(path: Path) -> dict:
    """Parse .env file → dict of key=value."""
    result = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return result

def extract_from_env(env: dict) -> dict:
    """Map env vars to secret fields."""
    secrets = {}
    for env_key, secret_key in ENV_MAP.items():
        val = env.get(env_key) or os.environ.get(env_key, "")
        if val and secret_key not in secrets:
            secrets[secret_key] = val
    return secrets

def try_onepassword(item_name: str) -> dict:
    """Fetch from 1Password CLI."""
    try:
        result = subprocess.run(
            ["op", "item", "get", item_name, "--format", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            secrets = {}
            for field in data.get("fields", []):
                label = field.get("label", "").lower().replace(" ", "_")
                value = field.get("value", "")
                if label in ENV_MAP.values() and value:
                    secrets[label] = value
            return secrets
    except Exception:
        pass
    return {}

def try_doppler() -> dict:
    """Fetch from Doppler CLI."""
    try:
        result = subprocess.run(
            ["doppler", "secrets", "download", "--no-file", "--format", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            env = json.loads(result.stdout)
            return extract_from_env(env)
    except Exception:
        pass
    return {}

def try_vault(path: str) -> dict:
    """Fetch from HashiCorp Vault CLI."""
    try:
        result = subprocess.run(
            ["vault", "kv", "get", "-format=json", path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            env = data.get("data", {}).get("data", data.get("data", {}))
            return extract_from_env(env)
    except Exception:
        pass
    return {}

def detect_vault_cli() -> list[str]:
    """Which vault CLIs are installed?"""
    found = []
    for cli in ["op", "doppler", "vault", "aws"]:
        try:
            subprocess.run([cli, "--version"], capture_output=True, timeout=3)
            found.append(cli)
        except Exception:
            pass
    return found

def prompt_interactive(manifest: dict) -> dict:
    """Ask user for secrets interactively. Skip if not needed."""
    mode = detect_mode(manifest, {})
    secrets = {}

    print("\nLet's configure your secrets.\n", flush=True)

    if mode in ("team", "enterprise"):
        hub_url = manifest.get("hub_url", "")
        if not hub_url:
            hub_url = input("  Hub URL (e.g. https://raven.acme.com): ").strip()
        if hub_url:
            secrets["hub_url"] = hub_url

        admin_email = input("  Admin email for alerts (Enter to skip): ").strip()
        if admin_email:
            secrets["admin_email"] = admin_email

        smtp_host = input("  SMTP host for email alerts (Enter to skip): ").strip()
        if smtp_host:
            secrets["smtp_host"] = smtp_host
            secrets["smtp_user"]     = input("  SMTP username: ").strip()
            secrets["smtp_password"] = getpass.getpass("  SMTP password: ")

        slack = input("  Slack webhook URL (Enter to skip): ").strip()
        if slack:
            secrets["slack_webhook"] = slack
    else:
        print("  Solo mode — no secrets required.", flush=True)
        print("  Email alerts and Hub disabled. Guards fully active.\n", flush=True)

    return secrets

def detect_mode(manifest: dict, secrets: dict) -> str:
    """Determine solo / team / enterprise from manifest + secrets."""
    hub_url = manifest.get("hub_url") or secrets.get("hub_url", "")
    org     = manifest.get("org", "")
    if hub_url and org:
        return "enterprise"
    if secrets.get("smtp_host") or secrets.get("slack_webhook") or secrets.get("admin_email"):
        return "team"
    return "solo"

def validate_mode(mode: str, secrets: dict, manifest: dict) -> tuple[bool, str]:
    """Halt check — only halt when REQUIRED secret is missing for the mode."""
    if mode == "enterprise":
        hub_url = manifest.get("hub_url") or secrets.get("hub_url", "")
        if not hub_url:
            return False, "Enterprise mode requires Hub URL. Set HUB_URL in .env or run /raven-init again."
    if mode == "team":
        has_notify = secrets.get("smtp_host") or secrets.get("slack_webhook")
        if not has_notify:
            return False, "Team mode requires email or Slack for approval flow. Add SMTP_HOST or SLACK_WEBHOOK to .env."
    return True, ""

def write_secrets(secrets: dict, source: str):
    """Write manifest.secrets.json — gitignored, never committed."""
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_source":     source,
        "_written_at": datetime.now(timezone.utc).isoformat(),
        **{k: v for k, v in secrets.items() if v},
    }
    SECRETS_PATH.write_text(json.dumps(payload, indent=2))

def ensure_gitignored():
    """Ensure .raven secrets are gitignored at project root."""
    gitignore = Path(".gitignore")
    raven_block = "\n# Raven\n.raven/manifest.secrets.json\n.raven/.cache/\n.model.env\n"
    content = gitignore.read_text() if gitignore.exists() else ""
    if ".raven/manifest.secrets.json" not in content:
        with open(gitignore, "a") as f:
            f.write(raven_block)

def print_outcome(mode: str, secrets: dict, source: str):
    features = {
        "Email alerts":  bool(secrets.get("smtp_host")),
        "Slack alerts":  bool(secrets.get("slack_webhook")),
        "Hub signal":    bool(secrets.get("hub_url")),
        "Audit log":     bool(secrets.get("audit_bucket")),
        "Guards":        True,
        "CVE check":     True,
        "Domain skills": True,
    }
    print(f"\n{'─'*42}", flush=True)
    print(f"  Secrets: {source}", flush=True)
    print(f"  Mode:    {mode}", flush=True)
    print(f"{'─'*42}", flush=True)
    for feature, active in features.items():
        icon = "✅" if active else "⚠️  disabled"
        print(f"  {icon}  {feature}", flush=True)
    print(f"{'─'*42}\n", flush=True)

def main():
    manifest = load_json(MANIFEST_PATH)
    secrets  = {}
    source   = "none"

    # 1. Try .env file
    if ENV_PATH.exists():
        env_vars = parse_env_file(ENV_PATH)
        secrets  = extract_from_env(env_vars)
        if secrets:
            source = ".env"
            print(f"✅ Secrets loaded from .env", flush=True)

    # 2. Try shell environment vars (in case .env not present but vars are exported)
    if not secrets:
        secrets = extract_from_env(dict(os.environ))
        if secrets:
            source = "shell environment"
            print(f"✅ Secrets loaded from shell environment", flush=True)

    # 3. Try vault CLIs
    if not secrets:
        vaults = detect_vault_cli()
        if vaults:
            print(f"\nNo .env found. Detected vault tools: {', '.join(vaults)}", flush=True)
            choice = input(f"  Fetch secrets from vault? (y/n): ").strip().lower()
            if choice == "y":
                if "op" in vaults:
                    item = input("  1Password item name: ").strip()
                    secrets = try_onepassword(item)
                    source  = "1password"
                elif "doppler" in vaults:
                    secrets = try_doppler()
                    source  = "doppler"
                elif "vault" in vaults:
                    path = input("  Vault secret path (e.g. secret/raven): ").strip()
                    secrets = try_vault(path)
                    source  = "hashicorp-vault"

    # 4. Interactive prompt
    if not secrets:
        choice = input("\nNo secrets found. Enter them now? (y/n — n = solo mode): ").strip().lower()
        if choice == "y":
            secrets = prompt_interactive(manifest)
            source  = "interactive"
        else:
            source = "solo-mode"

    # Detect mode and validate
    mode = detect_mode(manifest, secrets)
    ok, error = validate_mode(mode, secrets, manifest)
    if not ok:
        print(f"\n❌ {error}", file=sys.stderr)
        sys.exit(1)

    # Write secrets file (even if empty for solo — marks init as complete)
    if secrets:
        write_secrets(secrets, source)

    # Always ensure gitignore is correct
    ensure_gitignored()

    print_outcome(mode, secrets, source)

if __name__ == "__main__":
    main()
