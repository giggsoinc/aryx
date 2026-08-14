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

Split across three files: this module is the single-dataset entry point;
assemble_shared.py holds the role-filter/budget-cap/status rules both this
and the workspace-wide path apply identically; assemble_workspace.py is the
workspace-wide entry point (re-exported below for a single public import
surface: `from aryx.planning.assemble import assemble_context,
assemble_workspace_context`).
"""
from __future__ import annotations

from typing import Any

from aryx.planning.assemble_shared import (
    _MAX_PATHS,
    _context_status,
    _extract_approved_columns,
    _graph_path_hints,
    _graph_quality_notes,
    _tokens,
)
from aryx.planning.assemble_workspace import assemble_workspace_context
from aryx.planning.models import ApprovedColumn, PlanningContext, ResourceCitation

__all__ = ["assemble_context", "assemble_workspace_context"]


def _context_citations(intent: Any, dataset_profile: Any, dataset_version: str,
                       semantic_profile: Any, graph_profile: Any) -> list[ResourceCitation]:
    """Resource citations in retrieval order: intent, dataset profile,
    semantic profile, graph profile — whichever of the latter three exist."""
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
    return citations


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
    path_hints = _graph_path_hints(verified, _MAX_PATHS)
    quality_notes = _graph_quality_notes(graph_profile)

    # Steps 4/5 — catalogues + schema. Missing catalogue = hard stop.
    if not operations or not charts:
        warnings.append("missing approved operation/visualization catalogue")

    # Step 7 — resource citations.
    citations = _context_citations(intent, dataset_profile, dataset_version,
                                   semantic_profile, graph_profile)

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

    status = _context_status(bool(operations and charts), bool(approved),
                             "no approved columns — dataset has no analytically usable fields",
                             warnings)

    return PlanningContext(
        planning_context_id=f"planning_context_{dataset_id}_{dataset_version}",
        dataset_id=dataset_id, dataset_version=dataset_version,
        domain=domain, objective=objective,
        approved_columns=approved, approved_graph_paths=approved_paths,
        graph_path_hints=path_hints, graph_quality_notes=quality_notes,
        supported_operations=list(operations), supported_charts=list(charts),
        resource_citations=citations, completeness=completeness, relevance=relevance,
        warnings=warnings, context_status=status,
    )
