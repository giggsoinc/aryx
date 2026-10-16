#!/usr/bin/env python3
"""Resolve local component → Hub Project without manual manifest editing."""

from __future__ import annotations

import sys
from typing import Any

from project_link_common import (
    asset_id_token_needs_refresh,
    component_key,
    detect_git_remote,
    hub_get,
    load_project_link,
    project_root,
    repo_key_from_remote,
    repo_name_from_remote,
    resolve_asset_id_credentials,
    run_initial_inventory_scan,
    save_project_link,
)


def _merge_local_fields(link: dict[str, Any], *, remote: str) -> dict[str, Any]:
    key = component_key()
    remote = remote or detect_git_remote()
    link = dict(link)
    link.setdefault("component_key", key)
    link.setdefault("source_repo", remote)
    if remote:
        link.setdefault("repo_key", repo_key_from_remote(remote))
        link.setdefault("repo_name", repo_name_from_remote(remote, fallback=key))
    link["local_path"] = str(project_root())
    return link


def _attach_initial_scan(result: dict[str, Any]) -> dict[str, Any]:
    """Run a local-only scan after a fresh project link (greenfield bootstrap)."""
    if not result.get("ok"):
        return result
    if result.get("reason") == "cached":
        return result
    link = result.get("link") or {}
    scan = run_initial_inventory_scan(link=link)
    result["initial_scan"] = scan
    if scan.get("ok"):
        result["message"] = (
            f"Linked to {link.get('project_name', link.get('group_id'))}; "
            f"local scan found {scan.get('endpoints', 0)} endpoint(s). "
            "DB sync runs on git commit."
        )
    return result


def refresh_project_link(link: dict[str, Any] | None = None) -> dict[str, Any]:
    """Re-fetch project-link from Hub to mint a fresh Asset ID JWT."""

    cached = link or load_project_link()
    result = resolve(
        group_id=str(cached.get("group_id") or ""),
        remote=str(cached.get("source_repo") or ""),
        force=True,
    )
    if result.get("ok"):
        return result.get("link") or cached
    return cached


def resolve(*, group_id: str = "", remote: str = "", force: bool = False) -> dict[str, Any]:
    cached = load_project_link()
    if cached and not force and cached.get("application_id") and cached.get("group_id"):
        if not group_id or cached.get("group_id") == group_id:
            _base_url, token = resolve_asset_id_credentials(cached)
            if token and not asset_id_token_needs_refresh(token):
                return {"ok": True, "reason": "cached", "link": _merge_local_fields(cached, remote=remote)}

    remote = remote or detect_git_remote()
    if group_id:
        status, body = hub_get(
            "/api/v1/component-groups/project-link",
            params={
                "group_id": group_id,
                "component_key": component_key(),
                "source_repo": remote,
            },
        )
        if status in (200, 201):
            link = save_project_link(_merge_local_fields(body, remote=remote), linked_via="project_link")
            return _attach_initial_scan({"ok": True, "reason": "project_link", "link": link})
        return {"ok": False, "reason": "hub_error", "status": status, "message": body.get("detail", body)}

    if not remote:
        return {"ok": False, "reason": "no_repo", "message": "Could not detect git remote for this folder."}

    status, body = hub_get(
        "/api/v1/component-groups/resolve",
        params={"remote": remote, "component_key": component_key()},
    )
    if status not in (200, 201):
        return {"ok": False, "reason": "hub_error", "status": status, "message": body.get("detail", body)}

    groups = body.get("groups") or []
    if not groups:
        return {
            "ok": False,
            "reason": "no_project",
            "message": "No Hub Project claims this git remote. Add the remote in Raven Hub UI first.",
        }
    if len(groups) > 1 and not group_id:
        return {
            "ok": False,
            "reason": "ambiguous",
            "message": "Multiple Hub Projects match this git remote. Re-run with --project-id.",
            "groups": [{"group_id": g.get("group_id"), "project_name": g.get("project_name")} for g in groups],
        }

    chosen = next((g for g in groups if g.get("group_id") == group_id), groups[0])
    link = save_project_link(_merge_local_fields(chosen, remote=remote), linked_via="resolve_remote")
    return _attach_initial_scan({"ok": True, "reason": "resolve_remote", "link": link})


def main() -> int:
    import json

    args = sys.argv[1:]
    group_id = ""
    remote = ""
    force = False
    for index, arg in enumerate(args):
        if arg == "--project-id" and index + 1 < len(args):
            group_id = args[index + 1]
        elif arg == "--remote" and index + 1 < len(args):
            remote = args[index + 1]
        elif arg == "--force":
            force = True

    result = resolve(group_id=group_id, remote=remote, force=force)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 0


if __name__ == "__main__":
    sys.exit(main())
