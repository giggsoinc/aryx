"""Deterministic assembly of the planning context (C07) — mostly code.

Mirrors the component Procedure:
  1. resolve domain and objective keys (from the intent)
  2. select the matching approved catalogues (operations + charts)
  3. retrieve relevant dataset fields and graph paths (C03 + C06)
  4. attach supported operation and visualization catalogues
  5. attach validation rules and strict output schema (schema_version + status)
  6. exclude irrelevant or oversized context (role filter + budget cap)
  7. record resource ids, versions, rank, retrieval scores (citations)
  8. run completeness checks before planning (context_status + metrics)

Only approved, relevant resources enter the package; a missing catalogue is a
hard stop (context_status="blocked").
"""
from __future__ import annotations

import re
from typing import Any

from aryx.planning.models import (
    ApprovedColumn,
    DatasetColumns,
    PlanningContext,
    ResourceCitation,
)

# Roles that carry analytical value; text/attribute noise is excluded.
_APPROVED_ROLES = {"identifier", "measure", "dimension", "time", "status"}
_ROLE_RANK = {"identifier": 0, "time": 1, "measure": 2, "dimension": 3, "status": 4}
_MAX_COLUMNS = 40          # budget: keep the package small
_MAX_PATHS = 10
# Canonical (C03) type -> planning type label.
_TYPE_LABEL = {"datetime": "date"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}


def _extract_approved_columns(dataset_profile: Any) -> tuple[list[ApprovedColumn], list[str]]:
    """Role-filter + budget-cap one dataset's profiled columns.

    Shared by single-dataset and workspace-wide assembly so both scopes apply
    the exact same relevance/budget rules per dataset. Returns
    (approved_columns, warnings) — warnings are bare strings; the caller
    decides whether to prefix them with a dataset id.
    """
    columns = list(getattr(dataset_profile, "columns", []) or [])
    approved: list[ApprovedColumn] = []
    for col in columns:
        role = getattr(col, "candidate_role", "")
        if role not in _APPROVED_ROLES:
            continue
        ctype = getattr(col, "canonical_type", "")
        approved.append(ApprovedColumn(name=col.name, type=_TYPE_LABEL.get(ctype, ctype)))

    warnings: list[str] = []
    if len(approved) > _MAX_COLUMNS:
        by_role = {a.name: _ROLE_RANK.get(_role_of(columns, a.name), 9) for a in approved}
        approved.sort(key=lambda a: by_role[a.name])
        warnings.append(f"trimmed approved columns to {_MAX_COLUMNS} for budget "
                        f"(from {len(approved)})")
        approved = approved[:_MAX_COLUMNS]
    return approved, warnings


def assemble_context(
    *,
    dataset_id: str,
    dataset_version: str,
    dataset_profile: Any,
    semantic_profile: Any = None,
    graph_profile: Any = None,
    intent: Any = None,
    operations: list[str],
    charts: list[str],
    catalogue_version: str = "1.0",
) -> PlanningContext:
    """Assemble the smallest approved planning package from prior artifacts."""
    domain = getattr(intent, "domain", "") if intent else ""
    objective = getattr(intent, "objective", "") if intent else ""
    obj_tokens = _tokens(objective)
    warnings: list[str] = []

    # Steps 3/6 — relevant, approved columns (role filter + budget cap).
    columns = list(getattr(dataset_profile, "columns", []) or [])
    approved, col_warnings = _extract_approved_columns(dataset_profile)
    warnings.extend(col_warnings)

    # Step 3 — approved graph paths (already objective-ranked by C06).
    verified = list(getattr(graph_profile, "verified_paths", []) or [])
    approved_paths = [vp.path_id for vp in verified][:_MAX_PATHS]

    # Steps 4/5 — catalogues + schema. Missing catalogue = hard stop.
    if not operations or not charts:
        warnings.append("missing approved operation/visualization catalogue")

    # Step 7 — resource citations.
    citations: list[ResourceCitation] = []
    rank = 0
    if intent is not None:
        rank += 1
        citations.append(ResourceCitation(
            resource_id=getattr(intent, "request_id", ""), resource_type="user_intent",
            version=getattr(intent, "schema_version", ""), rank=rank))
    rank += 1
    citations.append(ResourceCitation(
        resource_id=getattr(dataset_profile, "dataset_profile_id", ""),
        resource_type="dataset_profile", version=dataset_version, rank=rank))
    if semantic_profile is not None:
        rank += 1
        citations.append(ResourceCitation(
            resource_id=getattr(semantic_profile, "semantic_profile_id", ""),
            resource_type="semantic_profile",
            version=getattr(semantic_profile, "dataset_version", ""), rank=rank))
    if graph_profile is not None:
        rank += 1
        citations.append(ResourceCitation(
            resource_id=getattr(graph_profile, "graph_profile_id", ""),
            resource_type="graph_profile",
            version=getattr(graph_profile, "graph_version", ""), rank=rank))

    # Step 8 — completeness + relevance metrics and status.
    grounded = len(getattr(semantic_profile, "annotations", []) or []) if semantic_profile else 0
    obj_hits = sum(1 for a in approved if _tokens(a.name) & obj_tokens) if obj_tokens else 0
    completeness = {
        "columns_total": len(columns),
        "columns_approved": len(approved),
        "columns_grounded": grounded,
        "graph_paths_available": len(verified),
        "has_intent": intent is not None,
        "has_semantic_profile": semantic_profile is not None,
        "has_graph_profile": graph_profile is not None,
    }
    relevance = {
        "objective_matched_columns": obj_hits,
        "objective_present": bool(obj_tokens),
    }

    if not operations or not charts:
        status = "blocked"
    elif not approved:
        status = "incomplete"
        warnings.append("no approved columns — dataset has no analytically usable fields")
    else:
        status = "complete"

    return PlanningContext(
        planning_context_id=f"planning_context_{dataset_id}_{dataset_version}",
        dataset_id=dataset_id, dataset_version=dataset_version,
        domain=domain, objective=objective,
        approved_columns=approved, approved_graph_paths=approved_paths,
        supported_operations=list(operations), supported_charts=list(charts),
        resource_citations=citations, completeness=completeness, relevance=relevance,
        warnings=warnings, context_status=status,
    )


def assemble_workspace_context(
    *,
    workspace_id: int,
    version: str,
    dataset_profiles: list[Any],
    semantic_profiles: dict[str, Any],
    graph_profile: Any = None,
    intent: Any = None,
    operations: list[str],
    charts: list[str],
) -> PlanningContext:
    """Assemble one merged planning context spanning every dataset in a workspace.

    Columns are kept grouped per dataset (`datasets`) rather than flattened —
    verified against real data that column names collide across unrelated
    datasets often enough (25 of 65 names in a single 21-dataset workspace)
    that a flat union would silently conflate different physical columns.
    `approved_columns` is still populated as a deduped union for display only;
    grounding code must use `datasets`, never the flat union.
    """
    domain = getattr(intent, "domain", "") if intent else ""
    objective = getattr(intent, "objective", "") if intent else ""
    obj_tokens = _tokens(objective)
    warnings: list[str] = []
    citations: list[ResourceCitation] = []
    rank = 0
    if intent is not None:
        rank += 1
        citations.append(ResourceCitation(
            resource_id=getattr(intent, "request_id", ""), resource_type="user_intent",
            version=getattr(intent, "schema_version", ""), rank=rank))

    datasets: list[DatasetColumns] = []
    total_columns = total_approved = total_grounded = 0
    for profile in dataset_profiles:
        did, dver = profile.dataset_id, profile.dataset_version
        columns = list(getattr(profile, "columns", []) or [])
        approved, col_warnings = _extract_approved_columns(profile)
        warnings.extend(f"{did}: {w}" for w in col_warnings)
        datasets.append(DatasetColumns(dataset_id=did, dataset_version=dver,
                                       approved_columns=approved))
        total_columns += len(columns)
        total_approved += len(approved)

        rank += 1
        citations.append(ResourceCitation(
            resource_id=profile.dataset_profile_id, resource_type="dataset_profile",
            version=dver, rank=rank))
        sem = semantic_profiles.get(did)
        if sem is not None:
            rank += 1
            citations.append(ResourceCitation(
                resource_id=sem.semantic_profile_id, resource_type="semantic_profile",
                version=sem.dataset_version, rank=rank))
            total_grounded += len(sem.annotations)

    if graph_profile is not None:
        rank += 1
        citations.append(ResourceCitation(
            resource_id=graph_profile.graph_profile_id, resource_type="graph_profile",
            version=graph_profile.graph_version, rank=rank))
    verified = list(getattr(graph_profile, "verified_paths", []) or [])
    approved_paths = [vp.path_id for vp in verified][:_MAX_PATHS]

    if not operations or not charts:
        warnings.append("missing approved operation/visualization catalogue")

    # Deduped union — display/back-compat convenience only, never for grounding.
    union_by_name: dict[str, ApprovedColumn] = {}
    for dc in datasets:
        for col in dc.approved_columns:
            union_by_name.setdefault(col.name, col)

    obj_hits = sum(1 for name in union_by_name if _tokens(name) & obj_tokens) if obj_tokens else 0
    completeness = {
        "dataset_count": len(datasets),
        "columns_total": total_columns,
        "columns_approved": total_approved,
        "columns_grounded": total_grounded,
        "graph_paths_available": len(verified),
        "has_intent": intent is not None,
        "has_graph_profile": graph_profile is not None,
    }
    relevance = {
        "objective_matched_columns": obj_hits,
        "objective_present": bool(obj_tokens),
    }

    if not operations or not charts:
        status = "blocked"
    elif not datasets or total_approved == 0:
        status = "incomplete"
        warnings.append("no approved columns across any dataset in this workspace")
    else:
        status = "complete"

    dataset_id = f"workspace_{workspace_id}"
    return PlanningContext(
        planning_context_id=f"planning_context_{dataset_id}_{version}",
        dataset_id=dataset_id, dataset_version=version,
        domain=domain, objective=objective,
        approved_columns=list(union_by_name.values()), datasets=datasets,
        approved_graph_paths=approved_paths,
        supported_operations=list(operations), supported_charts=list(charts),
        resource_citations=citations, completeness=completeness, relevance=relevance,
        warnings=warnings, context_status=status,
    )


def _role_of(columns: list[Any], name: str) -> str:
    for col in columns:
        if getattr(col, "name", None) == name:
            return getattr(col, "candidate_role", "")
    return ""
