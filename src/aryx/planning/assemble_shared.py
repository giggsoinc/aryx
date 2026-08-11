"""Helpers shared by single-dataset (assemble.py) and workspace-wide
(assemble_workspace.py) planning-context assembly (C07).

Role filter + budget cap, status rule, and graph-path/quality formatting —
identical rules both assembly scopes must apply so a chart-drafting LLM sees
the same guarantees regardless of scope.
"""
from __future__ import annotations

import re
from typing import Any

from aryx.planning.models import ApprovedColumn, GraphPathHint

# Roles that carry analytical value; text/attribute noise is excluded.
_APPROVED_ROLES = {"identifier", "measure", "dimension", "time", "status"}
_ROLE_RANK = {"identifier": 0, "time": 1, "measure": 2, "dimension": 3, "status": 4}
_MAX_COLUMNS = 40          # budget: keep the package small
_MAX_PATHS = 10
_MAX_SAMPLE_VALUES = 5     # budget: a handful of real example values per column
# Canonical (C03) type -> planning type label.
_TYPE_LABEL = {"datetime": "date"}


def _tokens(text: str) -> set[str]:
    """Lowercase word tokens from free text, for loose relevance matching."""
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}


def _extract_approved_columns(dataset_profile: Any) -> tuple[list[ApprovedColumn], list[str]]:
    """Role-filter + budget-cap one dataset's profiled columns.

    Shared by single-dataset and workspace-wide assembly so both scopes apply
    the exact same relevance/budget rules per dataset. Each returned
    `ApprovedColumn` also carries `cardinality` (ColumnProfile.unique_count)
    and `role` (candidate_role) straight through from the profile, so a
    chart-drafting LLM and the grounding chart-fitness check (ground.py) can
    tell a low-cardinality dimension from a high-cardinality one, and a time
    column from a plain dimension. Returns (approved_columns, warnings) —
    warnings are bare strings; the caller decides whether to prefix them
    with a dataset id.
    """
    columns = list(getattr(dataset_profile, "columns", []) or [])
    approved: list[ApprovedColumn] = []
    for col in columns:
        role = getattr(col, "candidate_role", "")
        if role not in _APPROVED_ROLES:
            continue
        ctype = getattr(col, "canonical_type", "")
        samples = list(getattr(col, "sample_values", []) or [])[:_MAX_SAMPLE_VALUES]
        approved.append(ApprovedColumn(
            name=col.name, type=_TYPE_LABEL.get(ctype, ctype), sample_values=samples,
            cardinality=getattr(col, "unique_count", 0), role=role))

    warnings: list[str] = []
    if len(approved) > _MAX_COLUMNS:
        by_role = {a.name: _ROLE_RANK.get(_role_of(columns, a.name), 9) for a in approved}
        approved.sort(key=lambda a: by_role[a.name])
        warnings.append(f"trimmed approved columns to {_MAX_COLUMNS} for budget "
                        f"(from {len(approved)})")
        approved = approved[:_MAX_COLUMNS]
    return approved, warnings


def _context_status(has_catalogues: bool, has_approved: bool, empty_warning: str,
                    warnings: list[str]) -> str:
    """blocked (no catalogue) / incomplete (no approved columns, appends a
    warning) / complete — the shared status rule both context shapes use."""
    if not has_catalogues:
        return "blocked"
    if not has_approved:
        warnings.append(empty_warning)
        return "incomplete"
    return "complete"


def _graph_path_hints(verified: list[Any], max_paths: int) -> list[GraphPathHint]:
    """Readable label per verified path — same cap/order as approved_graph_paths
    so every id in that allow-list has a matching hint (never the reverse)."""
    return [GraphPathHint(path_id=vp.path_id, label=" -> ".join(vp.path), depth=vp.depth)
           for vp in verified[:max_paths]]


def _graph_quality_notes(graph_profile: Any) -> list[str]:
    """Flatten C06's quality_flags + limitations into plain strings the
    prompt can embed directly — grounds the LLM's own 'assumptions' instead
    of it guessing at data-quality caveats."""
    if graph_profile is None:
        return []
    notes = [f"{f.code}: {f.detail}" if f.detail else f.code
            for f in (getattr(graph_profile, "quality_flags", []) or [])]
    notes.extend(getattr(graph_profile, "limitations", []) or [])
    return notes


def _role_of(columns: list[Any], name: str) -> str:
    """The candidate_role of the column named `name`, "" if not found."""
    for col in columns:
        if getattr(col, "name", None) == name:
            return getattr(col, "candidate_role", "")
    return ""
