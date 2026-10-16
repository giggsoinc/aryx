#!/usr/bin/env python3
"""Shared helpers for Raven project ↔ component linking and inventory commit flow."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

_PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))).resolve()
_RAVEN_DIR = _PROJECT / ".raven"
_MANIFEST = _RAVEN_DIR / "manifest.json"
_SECRETS = _RAVEN_DIR / "manifest.secrets.json"
_PROJECT_LINK = _RAVEN_DIR / "project-link.json"
_GLOBAL_CONFIG = Path.home() / ".claude" / "raven-config.json"
_STATE_DIR = _RAVEN_DIR / "state"
_INVENTORY_LOG = _STATE_DIR / "inventory-runs.jsonl"
_SCAN_REPORT = _STATE_DIR / "latest-scan-report.json"

_SSH_REMOTE_RE = re.compile(r"^git@([^:]+):(.+?)(\.git)?/?$", re.IGNORECASE)
_API_FILE_HINTS = (
    "/routes/", "/routers/", "/api/", "/handlers/", "/controllers/",
    "/endpoints/", "/views/",
)
_API_EXTENSIONS = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".java", ".rb"}


def project_root() -> Path:
    return _PROJECT


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def hub_identity() -> dict[str, str]:
    manifest = read_json(_MANIFEST)
    secrets = read_json(_SECRETS)
    global_cfg = read_json(_GLOBAL_CONFIG)
    return {
        "hub_url": manifest.get("hub_url") or secrets.get("hub_url") or global_cfg.get("hub_url") or "",
        "org": manifest.get("org") or secrets.get("org") or global_cfg.get("org") or "",
        "user_email": manifest.get("user_email") or global_cfg.get("dev_email") or "",
        "hub_token": secrets.get("hub_token") or global_cfg.get("hub_token") or "",
        "asset_id_base_url": (
            global_cfg.get("asset_id_base_url")
            or secrets.get("asset_id_base_url")
            or ""
        ),
    }


def resolve_asset_id_credentials(link: dict[str, Any] | None = None) -> tuple[str, str]:
    """Resolve Asset Identification base URL and Bearer token for local agents.

    Precedence (same pattern as hub_url / hub_token in the MCP installer flow):
      1. Process environment (explicit override)
      2. `.raven/project-link.json` from Hub (includes Hub-minted access_token)
      3. `.raven/manifest.secrets.json` (written on project link)
      4. `~/.claude/raven-config.json` (admin-provided base URL at install time)
    """

    link = link or load_project_link()
    asset = link.get("asset_identification") or {}
    secrets = read_json(_SECRETS)
    global_cfg = read_json(_GLOBAL_CONFIG)

    base_url = (
        os.environ.get("RAVEN_ASSET_ID_BASE_URL", "").strip()
        or str(asset.get("base_url") or "").strip()
        or str(secrets.get("asset_id_base_url") or "").strip()
        or str(global_cfg.get("asset_id_base_url") or "").strip()
    ).rstrip("/")

    token = (
        os.environ.get("RAVEN_ASSET_ID_TOKEN", "").strip()
        or str(asset.get("access_token") or "").strip()
        or str(secrets.get("asset_id_token") or "").strip()
        or str(global_cfg.get("asset_id_token") or "").strip()
    )
    return base_url, token


def jwt_expiry_epoch(token: str) -> int | None:
    """Return JWT ``exp`` claim without verifying the signature (stdlib-only)."""

    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + padding).decode("utf-8"))
        exp = data.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def asset_id_token_needs_refresh(token: str, *, skew_seconds: int | None = None) -> bool:
    """True when the Hub-minted Asset ID token is missing or near expiry."""

    if not token.strip():
        return True
    if os.environ.get("RAVEN_ASSET_ID_TOKEN", "").strip():
        return False
    exp = jwt_expiry_epoch(token)
    if exp is None:
        return False
    skew = skew_seconds
    if skew is None:
        skew = int(os.environ.get("RAVEN_ASSET_ID_TOKEN_REFRESH_SKEW_SECONDS", "3600"))
    return time.time() >= (exp - skew)


def apply_asset_id_credentials(
    link: dict[str, Any] | None = None,
    *,
    overwrite: bool = False,
) -> tuple[str, str]:
    """Resolve credentials and export them to the process environment."""

    base_url, token = resolve_asset_id_credentials(link)
    if base_url:
        if overwrite:
            os.environ["RAVEN_ASSET_ID_BASE_URL"] = base_url
        else:
            os.environ.setdefault("RAVEN_ASSET_ID_BASE_URL", base_url)
    if token:
        if overwrite:
            os.environ["RAVEN_ASSET_ID_TOKEN"] = token
        else:
            os.environ.setdefault("RAVEN_ASSET_ID_TOKEN", token)
    return base_url, token


def normalize_remote(remote: str) -> str:
    if not remote:
        return ""
    value = remote.strip().lower()
    match = _SSH_REMOTE_RE.match(value)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    value = re.sub(r"^[a-z]+://", "", value)
    value = re.sub(r"^[^/@]+@", "", value)
    value = value.rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value


def repo_key_from_remote(remote: str) -> str:
    normalized = normalize_remote(remote)
    if not normalized:
        return ""
    parts = normalized.split("/", 1)
    if len(parts) == 2 and parts[0] in ("github.com", "gitlab.com", "bitbucket.org"):
        return f"{parts[0].split('.')[0]}:{parts[1]}"
    return normalized.replace("/", ":")


def repo_name_from_remote(remote: str, *, fallback: str = "") -> str:
    normalized = normalize_remote(remote)
    if not normalized:
        return fallback
    return normalized.rsplit("/", 1)[-1] or fallback


def detect_git_remote(override: str = "") -> str:
    if override:
        return override.strip()
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=_PROJECT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    manifest = read_json(_MANIFEST)
    return manifest.get("git_remote", "")


def detect_git_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=_PROJECT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "main"


def component_key() -> str:
    link = load_project_link()
    if link.get("component_key"):
        return str(link["component_key"])
    return _PROJECT.name


def load_project_link() -> dict[str, Any]:
    return read_json(_PROJECT_LINK)


def save_project_link(link: dict[str, Any], *, linked_via: str) -> dict[str, Any]:
    payload = dict(link)
    payload["linked_at"] = datetime.now(timezone.utc).isoformat()
    payload["linked_via"] = linked_via
    write_json(_PROJECT_LINK, payload)

    asset = payload.get("asset_identification") or {}
    secrets = read_json(_SECRETS)
    changed = False
    if asset.get("access_token"):
        secrets["asset_id_token"] = asset["access_token"]
        changed = True
    if asset.get("base_url"):
        secrets["asset_id_base_url"] = asset["base_url"]
        changed = True
    if changed:
        write_json(_SECRETS, secrets)
    return payload


def hub_get(path: str, *, params: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    identity = hub_identity()
    hub_url = identity["hub_url"].rstrip("/")
    org = identity["org"]
    token = identity["hub_token"]
    if not (hub_url and org and token):
        return 0, {"detail": "Raven Hub is not configured on this machine"}

    query_params = dict(params or {})
    if identity.get("user_email") and "dev_email" not in query_params:
        query_params["dev_email"] = identity["user_email"]
    query = "&".join(f"{key}={urllib_request.quote(str(value))}" for key, value in query_params.items())
    url = f"{hub_url}{path}"
    if query:
        url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"
    if "org=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}org={urllib_request.quote(org)}"

    headers = {"X-Raven-Agent": token}
    if identity.get("user_email"):
        headers["X-Raven-User"] = identity["user_email"]
    req = urllib_request.Request(url, method="GET", headers=headers)
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
            return resp.status, body if isinstance(body, dict) else {"data": body}
    except urllib_error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8") or "{}")
        except Exception:
            body = {"detail": exc.reason}
        return exc.code, body
    except Exception as exc:
        return 0, {"detail": str(exc)[:300]}


def staged_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=_PROJECT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            return []
        return [line.strip() for line in out.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def looks_like_api_file(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    if suffix not in _API_EXTENSIONS:
        return False
    lowered = path.replace("\\", "/").lower()
    if any(hint in lowered for hint in _API_FILE_HINTS):
        return True
    return lowered.endswith(("main.py", "app.py", "server.py", "index.ts", "index.js"))


def append_inventory_log(entry: dict[str, Any]) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    with _INVENTORY_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")


def find_scanner_root() -> Path | None:
    """Optional external git_scanner checkout (RAVEN_SCANNER_ROOT only)."""
    candidate = os.environ.get("RAVEN_SCANNER_ROOT", "").strip()
    if not candidate:
        return None
    root = Path(candidate).resolve()
    if (root / "trinity_scanner" / "scanner.py").is_file():
        return root
    return None


def scan_report_path() -> Path:
    return _SCAN_REPORT


def load_cached_scan_report() -> dict[str, Any] | None:
    payload = read_json(_SCAN_REPORT)
    report = payload.get("report")
    return report if isinstance(report, dict) else None


def annotate_scan_report(report: dict[str, Any], *, component: str) -> dict[str, Any]:
    """Attach component_key and http_method to every endpoint in a scan report."""
    endpoints = report.get("endpoints") or []
    for endpoint in endpoints:
        endpoint["component_key"] = component
        entry = endpoint.get("entry_point") or {}
        if isinstance(entry, dict) and entry.get("method") and not endpoint.get("http_method"):
            endpoint["http_method"] = entry["method"]
    report["endpoints"] = endpoints
    return report


def run_endpoint_scan(repo_path: Path | None = None) -> dict[str, Any]:
    """Scan the local checkout. Uses the Raven skill scanner by default."""
    root = repo_path or project_root()
    scanner_root = find_scanner_root()
    if scanner_root is not None:
        with tempfile.TemporaryDirectory(prefix="raven-scan-") as tmp:
            sys_path = str(scanner_root)
            if sys_path not in sys.path:
                sys.path.insert(0, sys_path)
            from trinity_scanner.scanner import run_scan  # type: ignore

            return run_scan(
                repo_root=root,
                output_dir=Path(tmp),
                formats=["json"],
                analyze_prompts=os.environ.get("SCAN_ANALYZE_PROMPTS", "").lower() in ("1", "true", "yes"),
                probe_mcp_live=os.environ.get("SCAN_PROBE_MCP_LIVE", "").lower() in ("1", "true", "yes"),
            )

    from skill_route_scanner import run_skill_scan

    return run_skill_scan(root, repo_name=root.name)


def cache_scan_report(
    report: dict[str, Any],
    *,
    phase: str,
    link: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a local scan snapshot — used at init/link; DB ingest happens on commit."""
    component = (link or load_project_link()).get("component_key") or component_key()
    annotated = annotate_scan_report(dict(report), component=component)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "project": (link or {}).get("project_name"),
        "group_id": (link or {}).get("group_id"),
        "application_id": (link or {}).get("application_id"),
        "endpoints": len(annotated.get("endpoints") or []),
        "report": annotated,
    }
    write_json(_SCAN_REPORT, payload)
    return payload


def run_initial_inventory_scan(*, link: dict[str, Any] | None = None) -> dict[str, Any]:
    """Greenfield bootstrap: scan locally after project link; no Asset ID DB write."""
    active_link = link or load_project_link()
    if not active_link.get("application_id"):
        return {"ok": False, "error": "no_project_link"}
    try:
        report = run_endpoint_scan()
        cached = cache_scan_report(report, phase="init", link=active_link)
        return {
            "ok": True,
            "phase": "init",
            "endpoints": cached["endpoints"],
            "scan_report_path": str(_SCAN_REPORT),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:500]}
