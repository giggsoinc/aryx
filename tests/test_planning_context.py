"""Tests for Context and Resource Retrieval (C07) — pure, no DB."""
from __future__ import annotations

from aryx.planning.assemble import assemble_context, assemble_workspace_context
from aryx.planning.catalogues import CHARTS, OPERATIONS
from aryx.profiler.models import ColumnProfile, DatasetProfile
from aryx.graph_profiler.models import GraphProfile, VerifiedPath


def _profile() -> DatasetProfile:
    cols = [
        ColumnProfile(name="contract_id", original_type="string",
                      canonical_type="identifier", candidate_role="identifier"),
        ColumnProfile(name="region", original_type="string",
                      canonical_type="categorical", candidate_role="dimension"),
        ColumnProfile(name="contract_value", original_type="string",
                      canonical_type="numeric", candidate_role="measure"),
        ColumnProfile(name="renewal_status", original_type="string",
                      canonical_type="categorical", candidate_role="status"),
        ColumnProfile(name="contract_end_date", original_type="string",
                      canonical_type="datetime", candidate_role="time"),
        ColumnProfile(name="internal_notes", original_type="string",
                      canonical_type="text", candidate_role="attribute"),
    ]
    return DatasetProfile(
        dataset_profile_id="profile_dataset_contracts_v1",
        dataset_id="dataset_contracts", dataset_version="v1",
        row_count=1000, column_count=len(cols), columns=cols,
    )


def _graph() -> GraphProfile:
    return GraphProfile(
        graph_profile_id="graph_profile_graph_contracts_v1",
        graph_id="graph_contracts", graph_version="v1",
        verified_paths=[VerifiedPath(path_id="path_contract_manager_region",
                                     path=["Contract", "MANAGED_BY", "AccountManager"],
                                     depth=1)],
    )


def _assemble(**kw):
    base = dict(
        dataset_id="dataset_contracts", dataset_version="v1",
        dataset_profile=_profile(), graph_profile=_graph(),
        operations=OPERATIONS, charts=CHARTS,
    )
    base.update(kw)
    return assemble_context(**base)


def test_shape_and_status() -> None:
    ctx = _assemble()
    assert ctx.planning_context_id == "planning_context_dataset_contracts_v1"
    assert ctx.context_status == "complete"
    assert ctx.supported_operations == OPERATIONS
    assert ctx.supported_charts == CHARTS


def test_approved_columns_exclude_noise() -> None:
    ctx = _assemble()
    names = {c.name for c in ctx.approved_columns}
    assert "internal_notes" not in names           # text/attribute excluded
    assert names == {"contract_id", "region", "contract_value",
                     "renewal_status", "contract_end_date"}


def test_datetime_type_relabeled_as_date() -> None:
    ctx = _assemble()
    end = next(c for c in ctx.approved_columns if c.name == "contract_end_date")
    assert end.type == "date"


def test_approved_graph_paths() -> None:
    ctx = _assemble()
    assert ctx.approved_graph_paths == ["path_contract_manager_region"]


def test_citations_recorded() -> None:
    ctx = _assemble()
    types = {c.resource_type for c in ctx.resource_citations}
    assert "dataset_profile" in types and "graph_profile" in types
    assert all(c.rank >= 1 for c in ctx.resource_citations)


def test_completeness_metrics() -> None:
    ctx = _assemble()
    assert ctx.completeness["columns_total"] == 6
    assert ctx.completeness["columns_approved"] == 5
    assert ctx.completeness["graph_paths_available"] == 1
    assert ctx.completeness["has_graph_profile"] is True


def test_missing_catalogue_blocks() -> None:
    ctx = _assemble(charts=[])
    assert ctx.context_status == "blocked"
    assert any("catalogue" in w for w in ctx.warnings)


def test_no_usable_columns_is_incomplete() -> None:
    empty = DatasetProfile(
        dataset_profile_id="p", dataset_id="d", dataset_version="v1",
        row_count=1, column_count=1,
        columns=[ColumnProfile(name="notes", original_type="string",
                               canonical_type="text", candidate_role="attribute")],
    )
    ctx = _assemble(dataset_profile=empty)
    assert ctx.context_status == "incomplete"
    assert ctx.approved_columns == []


# ── assemble_workspace_context — merges ALL datasets, namespaced per dataset ──

def _item_profile() -> DatasetProfile:
    # 'model' collides with the customer/contract profile below on purpose —
    # this is the real collision shape found in production data (18/21
    # datasets in one workspace shared a column literally named 'model').
    cols = [
        ColumnProfile(name="model", original_type="string",
                      canonical_type="categorical", candidate_role="dimension"),
        ColumnProfile(name="fields.item_id", original_type="string",
                      canonical_type="identifier", candidate_role="identifier"),
        ColumnProfile(name="fields.cost", original_type="string",
                      canonical_type="numeric", candidate_role="measure"),
    ]
    return DatasetProfile(
        dataset_profile_id="profile_dataset_item_v1",
        dataset_id="dataset_item", dataset_version="v1",
        row_count=100, column_count=len(cols), columns=cols,
    )


def _demand_profile() -> DatasetProfile:
    cols = [
        ColumnProfile(name="model", original_type="string",
                      canonical_type="categorical", candidate_role="dimension"),
        ColumnProfile(name="fields.item_id", original_type="string",
                      canonical_type="identifier", candidate_role="identifier"),
        ColumnProfile(name="fields.quantity", original_type="string",
                      canonical_type="numeric", candidate_role="measure"),
    ]
    return DatasetProfile(
        dataset_profile_id="profile_dataset_demand_v1",
        dataset_id="dataset_demand", dataset_version="v1",
        row_count=220, column_count=len(cols), columns=cols,
    )


def test_workspace_context_groups_columns_by_dataset() -> None:
    ctx = assemble_workspace_context(
        workspace_id=23, version="v1",
        dataset_profiles=[_item_profile(), _demand_profile()],
        semantic_profiles={}, graph_profile=_graph(),
        operations=OPERATIONS, charts=CHARTS,
    )
    assert ctx.dataset_id == "workspace_23"
    assert ctx.planning_context_id == "planning_context_workspace_23_v1"
    assert {d.dataset_id for d in ctx.datasets} == {"dataset_item", "dataset_demand"}
    item_cols = {c.name for d in ctx.datasets if d.dataset_id == "dataset_item"
                 for c in d.approved_columns}
    demand_cols = {c.name for d in ctx.datasets if d.dataset_id == "dataset_demand"
                  for c in d.approved_columns}
    assert item_cols == {"model", "fields.item_id", "fields.cost"}
    assert demand_cols == {"model", "fields.item_id", "fields.quantity"}


def test_workspace_context_flat_union_is_display_only_not_ambiguous_grounding() -> None:
    # The collision itself: 'model' and 'fields.item_id' both appear in TWO
    # datasets. The flat `approved_columns` union must still exist (display),
    # but `datasets` is what preserves which dataset each one really came
    # from — that's the whole point of not flattening for grounding.
    ctx = assemble_workspace_context(
        workspace_id=1, version="v1",
        dataset_profiles=[_item_profile(), _demand_profile()],
        semantic_profiles={}, operations=OPERATIONS, charts=CHARTS,
    )
    union_names = {c.name for c in ctx.approved_columns}
    assert union_names == {"model", "fields.item_id", "fields.cost", "fields.quantity"}
    assert len(ctx.datasets) == 2  # collision preserved as 2 separate groups, not merged into 1


def test_workspace_context_completeness_aggregates_across_datasets() -> None:
    ctx = assemble_workspace_context(
        workspace_id=1, version="v1",
        dataset_profiles=[_item_profile(), _demand_profile()],
        semantic_profiles={}, operations=OPERATIONS, charts=CHARTS,
    )
    assert ctx.completeness["dataset_count"] == 2
    assert ctx.completeness["columns_total"] == 6
    assert ctx.completeness["columns_approved"] == 6


def test_workspace_context_citations_include_every_dataset() -> None:
    ctx = assemble_workspace_context(
        workspace_id=1, version="v1",
        dataset_profiles=[_item_profile(), _demand_profile()],
        semantic_profiles={}, operations=OPERATIONS, charts=CHARTS,
    )
    profile_citations = [c for c in ctx.resource_citations if c.resource_type == "dataset_profile"]
    assert {c.resource_id for c in profile_citations} == {
        "profile_dataset_item_v1", "profile_dataset_demand_v1"}


def test_workspace_context_empty_datasets_is_none_upstream() -> None:
    # run.py returns None when no dataset has been profiled yet; assemble
    # itself just reflects whatever it's given, so test the boundary here:
    # zero profiles -> incomplete status, not a crash.
    ctx = assemble_workspace_context(
        workspace_id=1, version="v1", dataset_profiles=[],
        semantic_profiles={}, operations=OPERATIONS, charts=CHARTS,
    )
    assert ctx.context_status == "incomplete"
    assert ctx.datasets == []
