#!/usr/bin/env python3
"""Validation and ingest payload helpers for Raven skill scanning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_link_common import (
    annotate_scan_report,
    component_key,
    detect_git_branch,
    detect_git_remote,
    load_project_link,
    project_root,
    repo_key_from_remote,
    repo_name_from_remote,
)


_REQUIRED_ENTRY_FIELDS = ("kind", "handler_function", "handler_file", "handler_line", "method", "path")


def validate_scan_report(report: dict[str, Any]) -> list[str]:
    """Return validation errors; empty list means the report can be ingested."""
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report must be a JSON object"]
    endpoints = report.get("endpoints")
    if not isinstance(endpoints, list):
        return ["report.endpoints must be a list"]
    if not endpoints:
        errors.append("report.endpoints is empty — scan found no HTTP routes")

    for index, endpoint in enumerate(endpoints):
        prefix = f"endpoints[{index}]"
        if not isinstance(endpoint, dict):
            errors.append(f"{prefix} must be an object")
            continue
        entry = endpoint.get("entry_point") or {}
        if not isinstance(entry, dict):
            errors.append(f"{prefix}.entry_point must be an object")
            continue
        for field in _REQUIRED_ENTRY_FIELDS:
            if not entry.get(field):
                errors.append(f"{prefix}.entry_point.{field} is required")
        if entry.get("kind") != "http":
            errors.append(f"{prefix}.entry_point.kind must be http")
        for child_key in ("llm_assets", "mcp_assets", "agent_assets", "rag_assets"):
            value = endpoint.get(child_key, [])
            if value is None:
                endpoint[child_key] = []
            elif not isinstance(value, list):
                errors.append(f"{prefix}.{child_key} must be a list")

    meta = report.get("meta")
    if meta is not None and not isinstance(meta, dict):
        errors.append("report.meta must be an object")
    return errors


def load_scan_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("report"), dict):
        return payload["report"]
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"Invalid scan report format: {path}")


def write_scan_report(report: dict[str, Any], path: Path, *, phase: str = "skill-scan") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": phase,
        "report": report,
        "endpoints": len(report.get("endpoints") or []),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def build_inventory_payload(
    report: dict[str, Any],
    link: dict[str, Any] | None = None,
    *,
    prune_missing: bool = True,
) -> dict[str, Any]:
    """Build an Asset Identification ingest payload from a skill scan report."""
    active = link or load_project_link()
    if not active.get("application_id") or not active.get("organization_id"):
        raise RuntimeError("project link is missing application_id or organization_id")

    remote = active.get("source_repo") or detect_git_remote()
    component = active.get("component_key") or component_key()
    repo_key = active.get("repo_key") or repo_key_from_remote(remote) or f"local:{component}"
    repo_name = active.get("repo_name") or repo_name_from_remote(remote, fallback=component)
    annotated = annotate_scan_report(dict(report), component=component)

    return {
        "application_id": active["application_id"],
        "organization_id": active["organization_id"],
        "raven_project_id": active.get("raven_project_id") or active.get("group_id"),
        "repositories": [{
            "repo_key": repo_key,
            "repo_name": repo_name,
            "repo_path": str(project_root()),
            "branch_name": detect_git_branch(),
            "report": annotated,
            "prune_missing": prune_missing,
        }],
    }
