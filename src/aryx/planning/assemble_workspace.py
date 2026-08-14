"""Workspace-wide planning-context assembly (C07) — one merged context
spanning every dataset in a workspace. See assemble.py's module docstring
for the full C07 procedure this and the single-dataset path both implement.
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
from aryx.planning.models import ApprovedColumn, DatasetColumns, PlanningContext, ResourceCitation


def _collect_workspace_datasets(
    dataset_profiles: list[Any],
) -> tuple[list[DatasetColumns], list[str], int, int]:
    """Per-dataset approved columns + running totals (columns_total,
    columns_approved) — citations for these same profiles are built
    separately by `_workspace_citations`, iterating in the same order."""
    datasets: list[DatasetColumns] = []
    warnings: list[str] = []
    total_columns = total_approved = 0
    for profile in dataset_profiles:
        did, dver = profile.dataset_id, profile.dataset_version
        columns = list(getattr(profile, "columns", []) or [])
        approved, col_warnings = _extract_approved_columns(profile)
        warnings.extend(f"{did}: {w}" for w in col_warnings)
        datasets.append(DatasetColumns(dataset_id=did, dataset_version=dver,
                                       approved_columns=approved))
        total_columns += len(columns)
        total_approved += len(approved)
    return datasets, warnings, total_columns, total_approved


def _workspace_citations(intent: Any, dataset_profiles: list[Any],
                         semantic_profiles: dict[str, Any],
                         graph_profile: Any) -> tuple[list[ResourceCitation], int]:
    """Resource citations in retrieval order: intent, then each dataset's
    (dataset_profile, semantic_profile) pair, then graph_profile. Returns
    (citations, total_grounded) since grounded-annotation counting only
    happens here, alongside the semantic-profile lookup it already needs."""
    citations: list[ResourceCitation] = []
    rank = 0
    total_grounded = 0
    if intent is not None:
        rank += 1
        citations.append(ResourceCitation(
            resource_id=getattr(intent, "request_id", ""), resource_type="user_intent",
            version=getattr(intent, "schema_version", ""), rank=rank))
    for profile in dataset_profiles:
        did, dver = profile.dataset_id, profile.dataset_version
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
    return citations, total_grounded


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

    datasets, warnings, total_columns, total_approved = _collect_workspace_datasets(dataset_profiles)
    citations, total_grounded = _workspace_citations(intent, dataset_profiles,
                                                      semantic_profiles, graph_profile)

    verified = list(getattr(graph_profile, "verified_paths", []) or [])
    approved_paths = [vp.path_id for vp in verified][:_MAX_PATHS]
    path_hints = _graph_path_hints(verified, _MAX_PATHS)
    quality_notes = _graph_quality_notes(graph_profile)

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

    status = _context_status(bool(operations and charts), bool(datasets and total_approved),
                             "no approved columns across any dataset in this workspace",
                             warnings)

    dataset_id = f"workspace_{workspace_id}"
    return PlanningContext(
        planning_context_id=f"planning_context_{dataset_id}_{version}",
        dataset_id=dataset_id, dataset_version=version,
        domain=domain, objective=objective,
        approved_columns=list(union_by_name.values()), datasets=datasets,
        approved_graph_paths=approved_paths,
        graph_path_hints=path_hints, graph_quality_notes=quality_notes,
        supported_operations=list(operations), supported_charts=list(charts),
        resource_citations=citations, completeness=completeness, relevance=relevance,
        warnings=warnings, context_status=status,
    )
