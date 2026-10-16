#!/usr/bin/env python3
"""Raven asset inventory commit hooks — pre-commit validation and post-commit sync."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CORE_DIR = Path(__file__).resolve().parent
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

from project_link_common import (  # noqa: E402
    append_inventory_log,
    annotate_scan_report,
    apply_asset_id_credentials,
    asset_id_token_needs_refresh,
    component_key,
    detect_git_branch,
    detect_git_remote,
    hub_identity,
    looks_like_api_file,
    load_project_link,
    project_root,
    repo_key_from_remote,
    repo_name_from_remote,
    resolve_asset_id_credentials,
    run_endpoint_scan,
    staged_files,
)
from project_resolve import refresh_project_link, resolve  # noqa: E402


def _inventory_cli_path() -> Path | None:
    candidates = [
        project_root() / "agent" / "scripts" / "raven-asset-inventory.py",
        _CORE_DIR.parent / "agent" / "scripts" / "raven-asset-inventory.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _ensure_project_context() -> dict[str, Any]:
    link = load_project_link()
    if link.get("application_id") and link.get("organization_id"):
        _, token = resolve_asset_id_credentials(link)
        if token and not asset_id_token_needs_refresh(token):
            return link
        refreshed = refresh_project_link(link)
        if refreshed.get("application_id"):
            return refreshed
        return link

    result = resolve()
    if not result.get("ok"):
        return {}
    return result.get("link") or {}


def _annotate_report(report: dict[str, Any], *, component: str) -> dict[str, Any]:
    return annotate_scan_report(report, component=component)


def _run_scan(repo_path: Path, *, output_dir: Path) -> dict[str, Any]:
    del output_dir  # run_endpoint_scan manages its own temp dir
    return run_endpoint_scan(repo_path)


def _build_inventory_payload(link: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    remote = link.get("source_repo") or detect_git_remote()
    component = link.get("component_key") or component_key()
    repo_key = link.get("repo_key") or repo_key_from_remote(remote) or f"local:{component}"
    repo_name = link.get("repo_name") or repo_name_from_remote(remote, fallback=component)
    return {
        "application_id": link["application_id"],
        "organization_id": link["organization_id"],
        "raven_project_id": link.get("raven_project_id") or link.get("group_id"),
        "repositories": [{
            "repo_key": repo_key,
            "repo_name": repo_name,
            "repo_path": str(project_root()),
            "branch_name": detect_git_branch(),
            "report": _annotate_report(report, component=component),
            "prune_missing": True,
        }],
    }


def _inventory_auth_failure(proc: subprocess.CompletedProcess[str]) -> bool:
    text = f"{proc.stderr or ''}\n{proc.stdout or ''}".lower()
    if "http 401" in text or "token has expired" in text or "unauthorized" in text:
        return True
    try:
        body = json.loads(proc.stdout or "{}")
        detail = str(body.get("detail", "")).lower()
        return "401" in detail or "expired" in detail or "unauthorized" in detail
    except json.JSONDecodeError:
        return False


def _require_asset_id_credentials(link: dict[str, Any]) -> None:
    base_url, token = resolve_asset_id_credentials(link)
    if not base_url:
        raise RuntimeError(
            "Asset Identification base URL is not configured. "
            "Run project link after Hub RAVEN_ASSET_ID_BASE_URL is set, "
            "or set asset_id_base_url in ~/.claude/raven-config.json at install time."
        )
    if not token:
        raise RuntimeError(
            "Asset Identification token is not configured. "
            "Re-run `python raven-core/raven-project-link.py` so Hub can mint a token, "
            "or set RAVEN_ASSET_ID_TOKEN for a manual override."
        )


def _submit_inventory(payload: dict[str, Any]) -> dict[str, Any]:
    cli = _inventory_cli_path()
    if cli is None:
        raise RuntimeError("agent/scripts/raven-asset-inventory.py not found")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle)
        payload_path = handle.name

    try:
        for attempt in range(2):
            if attempt == 1:
                refreshed = refresh_project_link(load_project_link())
                apply_asset_id_credentials(refreshed, overwrite=True)
            else:
                apply_asset_id_credentials(load_project_link())

            _require_asset_id_credentials(load_project_link())

            proc = subprocess.run(
                [sys.executable, str(cli), "--operation", "ingest", "--payload-file", payload_path],
                cwd=str(project_root()),
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("RAVEN_INVENTORY_TIMEOUT", "180")),
            )
            if proc.returncode == 0:
                try:
                    return json.loads(proc.stdout or "{}")
                except json.JSONDecodeError:
                    return {"stdout": proc.stdout, "stderr": proc.stderr}

            if attempt == 0 and _inventory_auth_failure(proc):
                continue
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "inventory ingest failed")
        raise RuntimeError("inventory ingest failed")
    finally:
        try:
            Path(payload_path).unlink(missing_ok=True)
        except Exception:
            pass


def run_pre_commit() -> int:
    if os.environ.get("RAVEN_SKIP_INVENTORY_HOOK", "").strip():
        return 0

    changed = [path for path in staged_files() if looks_like_api_file(path)]
    if not changed:
        return 0

    link = _ensure_project_context()
    if not link:
        print("ℹ️  raven-asset-inventory: no project link — run `python raven-core/raven-project-link.py`")
        return 0

    print(f"▶ raven-asset-inventory: {len(changed)} API file(s) staged — project {link.get('project_name', link.get('group_id'))}")
    if os.environ.get("RAVEN_INVENTORY_STRICT", "").strip():
        identity = hub_identity()
        link = load_project_link()
        base_url, token = resolve_asset_id_credentials(link)
        missing = [name for name, value in (
            ("asset_id_token", token),
            ("asset_id_base_url", base_url),
            ("hub_token", identity.get("hub_token", "")),
        ) if not value]
        if missing:
            print(f"❌ raven-asset-inventory: missing {', '.join(missing)}")
            return 1
    return 0


def run_post_commit() -> int:
    if os.environ.get("RAVEN_SKIP_INVENTORY_HOOK", "").strip():
        return 0

    link = _ensure_project_context()
    if not link:
        print("ℹ️  raven-asset-inventory: skipped — no project link")
        return 0

    try:
        with tempfile.TemporaryDirectory(prefix="raven-scan-") as tmp:
            report = _run_scan(project_root(), output_dir=Path(tmp))
        payload = _build_inventory_payload(link, report)
        result = _submit_inventory(payload)
        append_inventory_log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "phase": "post-commit",
            "project": link.get("project_name"),
            "group_id": link.get("group_id"),
            "application_id": link.get("application_id"),
            "endpoints": len((report.get("endpoints") or [])),
            "result": result,
        })
        data = result.get("data") or result
        created = data.get("endpoints_created", 0)
        updated = data.get("endpoints_updated", 0)
        print(f"✅ raven-asset-inventory: DB sync — {created} created, {updated} updated")
        return 0
    except Exception as exc:
        append_inventory_log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "phase": "post-commit",
            "error": str(exc)[:500],
        })
        print(f"⚠️  raven-asset-inventory: sync failed — {exc}")
        return 0


def main() -> int:
    phase = "post-commit"
    args = sys.argv[1:]
    for index, arg in enumerate(args):
        if arg == "--phase" and index + 1 < len(args):
            phase = args[index + 1]
    if phase == "pre-commit":
        return run_pre_commit()
    return run_post_commit()


if __name__ == "__main__":
    sys.exit(main())
