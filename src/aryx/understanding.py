"""Data understanding — Aryx's read-only reading of the ingested data.

Architecture (restored from v1.5.3, regressed in 1.8.0): the CUSTOMER
authors the brief BEFORE any upload. `aryx_workspace.brief` is therefore
customer-owned and authoritative. What the pipeline infers from data
samples after upload is a separate, read-only artifact stored in
`aryx_workspace.data_understanding` and shown as an info tab.

The single exception is the soft gate: a customer who skipped the brief
step has an empty brief, so the derived reading is promoted into it and
stamped `brief_source='derived'` so downstream code knows it was not
human-authored.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from aryx.brief import is_populated
from aryx.workspaces import WorkspaceStore

logger = logging.getLogger(__name__)

_LIST_FIELDS = ("objectives", "roles", "questions")


def normalize_lists(brief: dict[str, Any]) -> dict[str, Any]:
    """Coerce newline-joined textarea values back into lists."""
    out = dict(brief or {})
    for key in _LIST_FIELDS:
        value = out.get(key)
        if isinstance(value, str):
            out[key] = [line.strip() for line in value.splitlines() if line.strip()]
    return out


def customer_brief(store: WorkspaceStore, workspace_id: int) -> dict[str, Any]:
    """The brief the customer authored before uploading, or {} if skipped."""
    try:
        return store.get_understanding(workspace_id).get("brief") or {}
    except Exception:
        logger.debug("customer brief lookup failed ws=%s", workspace_id,
                     exc_info=True)
        return {}


def build_record(derived: dict[str, Any], plan: dict[str, Any],
                 result: dict[str, Any], source_files: list[str],
                 promoted: bool) -> dict[str, Any]:
    """Assemble the `data_understanding` JSONB payload."""
    return {
        "summary": str(result.get("summary") or ""),
        "brief": derived,
        "graph_plan": plan or {},
        "divergences": result.get("divergences") or [],
        "gaps": result.get("gaps") or [],
        "source_files": source_files,
        "fallback": bool(result.get("fallback")),
        "generated_at": datetime.now(UTC).isoformat(),
        "promoted_to_brief": promoted,
    }


def record(store: WorkspaceStore, workspace_id: int, derived: dict[str, Any],
           plan: dict[str, Any], result: dict[str, Any],
           source_files: list[str] | None = None) -> dict[str, Any]:
    """Persist the derived reading; return the brief that stays authoritative.

    Returns `{"brief", "brief_source", "promoted"}`. Never overwrites a
    populated customer brief.
    """
    derived = normalize_lists(derived)
    existing = customer_brief(store, workspace_id)

    # The promote is attempted through a single guarded UPDATE rather than
    # decided here: a customer can save their brief between this read and
    # that write, and read-then-write would overwrite it. `existing` is
    # therefore only a hint for what to record — the database arbitrates.
    promoted_row = (None if is_populated(existing)
                    else store.promote_derived_brief(workspace_id, derived))
    promoted = promoted_row is not None

    store.set_understanding(workspace_id, build_record(
        derived, plan or {}, result or {}, source_files or [], promoted))

    if promoted:
        logger.info("no customer brief ws=%s — promoted derived brief",
                    workspace_id)
        return {"brief": derived, "brief_source": "derived", "promoted": True}

    # Either the customer already had a brief, or they saved one while this
    # ran. Re-read so the caller reports what actually survived, not the
    # stale value read at the top.
    surviving = customer_brief(store, workspace_id) or existing
    logger.info("customer brief preserved ws=%s — derived reading stored "
                "read-only", workspace_id)
    return {"brief": surviving, "brief_source": "customer", "promoted": False}


def stash_plan_context(store: WorkspaceStore, workspace_id: int,
                       brief: dict[str, Any], plan: dict[str, Any]) -> None:
    """Write a compact plan summary into workspace context for extractors.

    Sourced from the CUSTOMER brief (or the promoted derived one), so the
    extraction prompts inherit the goal the customer actually stated.
    """
    try:
        bits: list[str] = []
        if brief.get("domain"):
            bits.append(f"Domain: {brief['domain']}")
        outcomes = (plan.get("outcomes") or [])[:6]
        if outcomes:
            bits.append("Graph outcomes: " + "; ".join(str(o) for o in outcomes))
        names = [p.get("name") for p in (plan.get("primary_types") or [])
                 if isinstance(p, dict)]
        names += [d.get("name") for d in (plan.get("dimension_types") or [])
                  if isinstance(d, dict)]
        if names:
            bits.append("Planned entity types: " + ", ".join(str(n) for n in names))
        if bits:
            store.set_context(workspace_id, "\n".join(bits))
    except Exception:
        logger.debug("context stash skipped", exc_info=True)
