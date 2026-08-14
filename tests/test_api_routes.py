"""Route-contract tests for the read/list/run API routers that had zero
direct test coverage (raven-review finding): dataset, execution_plan,
execution_run, graph_intake, graph_profile, intent, planning_context,
profile, semantic, dashboard_model, render_telemetry, datasource.

Scope is deliberately the ROUTING contract, not full domain behavior (each
domain module already has its own dedicated tests): every store-backed
GET-by-id 404s cleanly when nothing exists, every /versions list returns
whatever the store gives back, and datasource_api's plain-dict routes are
exercised end to end since they need no Pydantic model construction. Store
classes and domain run_*() functions are mocked at the exact import path
each api module holds them under — the router itself is what's under test.

`get_settings` is mocked in every test too: the real Settings() reads this
machine's local .env, which carries Docker-only keys `Settings` (extra=
"forbid") rejects outside a container — unrelated to the routes themselves.
"""
from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class _PatchedClient:
    """Wraps TestClient so the get_settings/store patches are torn down
    right after the ONE request each test makes — `ExitStack.enter_context`
    with no matching `close()` would otherwise leak every patch past the
    test, permanently monkey-patching the real store classes for the rest
    of the pytest process (confirmed live before this wrapper existed)."""

    def __init__(self, app: FastAPI, stack: ExitStack) -> None:
        self._client = TestClient(app, raise_server_exceptions=False)
        self._stack = stack

    def __getattr__(self, name: str):
        method = getattr(self._client, name)
        def call(*args, **kwargs):
            try:
                return method(*args, **kwargs)
            finally:
                self._stack.close()
        return call


def _client(router_factory, module: str, **mocks) -> _PatchedClient:
    """Mount `router_factory`'s router with `get_settings` and every
    name in `mocks` patched on `module`, e.g. mocks=dict(DatasetStore=...)."""
    stack = ExitStack()
    stack.enter_context(patch(f"{module}.get_settings",
                              return_value=MagicMock(rdb_dsn="postgresql://test")))
    for name, target in mocks.items():
        stack.enter_context(patch(f"{module}.{name}", target))
    app = FastAPI()
    app.include_router(router_factory())
    return _PatchedClient(app, stack)


def test_dataset_get_404_when_missing():
    from aryx.api.dataset_api import dataset_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(dataset_router, "aryx.api.dataset_api",
                   DatasetStore=store_cls).get("/dataset/nope")
    assert resp.status_code == 404


def test_dataset_versions_returns_store_list():
    from aryx.api.dataset_api import dataset_router
    store_cls = MagicMock()
    store_cls.return_value.list_versions.return_value = []
    resp = _client(dataset_router, "aryx.api.dataset_api",
                   DatasetStore=store_cls).get("/dataset/versions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_execution_plan_get_404_when_missing():
    from aryx.api.execution_plan_api import execution_plan_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(execution_plan_router, "aryx.api.execution_plan_api",
                   ExecutionPlanStore=store_cls).get("/execution-plan/ds1")
    assert resp.status_code == 404


def test_execution_plan_versions_empty():
    from aryx.api.execution_plan_api import execution_plan_router
    store_cls = MagicMock()
    store_cls.return_value.list.return_value = []
    resp = _client(execution_plan_router, "aryx.api.execution_plan_api",
                   ExecutionPlanStore=store_cls).get("/execution-plan/versions")
    assert resp.status_code == 200 and resp.json() == []


def test_execution_run_workspace_null_when_missing():
    from aryx.api.execution_run_api import execution_run_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(execution_run_router, "aryx.api.execution_run_api",
                   ExecutionRunStore=store_cls).get("/execution-run/workspace")
    # response_model is `ExecutionRun | None` — null is a valid 200, not a 404.
    assert resp.status_code == 200 and resp.json() is None


def test_execution_run_versions_requires_dataset_id():
    from aryx.api.execution_run_api import execution_run_router
    resp = _client(execution_run_router, "aryx.api.execution_run_api").get(
        "/execution-run/versions")
    assert resp.status_code == 422  # dataset_id is a required query param


def test_graph_intake_run_404_when_no_entities():
    from aryx.api.graph_intake_api import graph_intake_router
    resp = _client(graph_intake_router, "aryx.api.graph_intake_api",
                   run_intake=MagicMock(return_value=None)).post("/graph-intake/run")
    assert resp.status_code == 404


def test_graph_intake_get_404_when_missing():
    from aryx.api.graph_intake_api import graph_intake_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(graph_intake_router, "aryx.api.graph_intake_api",
                   GraphIntakeStore=store_cls).get("/graph-intake/g1")
    assert resp.status_code == 404


def test_graph_profile_run_404_when_no_validated_graph():
    from aryx.api.graph_profile_api import graph_profile_router
    resp = _client(graph_profile_router, "aryx.api.graph_profile_api",
                   run_graph_profile=MagicMock(return_value=None)).post(
        "/graph-profile/run", json={})
    assert resp.status_code == 404


def test_graph_profile_get_404_when_missing():
    from aryx.api.graph_profile_api import graph_profile_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(graph_profile_router, "aryx.api.graph_profile_api",
                   GraphProfileStore=store_cls).get("/graph-profile/g1")
    assert resp.status_code == 404


def test_intent_get_capture_404_when_missing():
    from aryx.api.intent_api import intent_router
    store_cls = MagicMock()
    store_cls.return_value.get.return_value = None
    resp = _client(intent_router, "aryx.api.intent_api",
                   IntentStore=store_cls).get("/intent/req-1")
    assert resp.status_code == 404


def test_intent_captures_empty():
    from aryx.api.intent_api import intent_router
    store_cls = MagicMock()
    store_cls.return_value.list.return_value = []
    resp = _client(intent_router, "aryx.api.intent_api",
                   IntentStore=store_cls).get("/intent/captures")
    assert resp.status_code == 200 and resp.json() == []


def test_planning_context_run_404_when_no_profile():
    from aryx.api.planning_context_api import planning_context_router
    resp = _client(planning_context_router, "aryx.api.planning_context_api",
                   run_context=MagicMock(return_value=None)).post(
        "/planning-context/run", json={"dataset_id": "ds1"})
    assert resp.status_code == 404


def test_planning_context_workspace_run_404_when_nothing_profiled():
    from aryx.api.planning_context_api import planning_context_router
    resp = _client(planning_context_router, "aryx.api.planning_context_api",
                   run_workspace_context=MagicMock(return_value=None)).post(
        "/planning-context/workspace/run")
    assert resp.status_code == 404


def test_planning_context_get_404_when_missing():
    from aryx.api.planning_context_api import planning_context_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(planning_context_router, "aryx.api.planning_context_api",
                   ContextStore=store_cls).get("/planning-context/ds1")
    assert resp.status_code == 404


def test_profile_run_404_when_no_snapshot():
    from aryx.api.profile_api import profile_router
    resp = _client(profile_router, "aryx.api.profile_api",
                   run_profile=MagicMock(return_value=None)).post(
        "/profile/run", json={"dataset_id": "ds1"})
    assert resp.status_code == 404


def test_profile_get_404_when_missing():
    from aryx.api.profile_api import profile_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(profile_router, "aryx.api.profile_api",
                   ProfileStore=store_cls).get("/profile/ds1")
    assert resp.status_code == 404


def test_semantic_run_404_when_no_profile():
    from aryx.api.semantic_api import semantic_router
    resp = _client(semantic_router, "aryx.api.semantic_api",
                   _local_broker=MagicMock(return_value=MagicMock()),
                   run_interpret=MagicMock(return_value=None)).post(
        "/semantic/run", json={"dataset_id": "ds1"})
    assert resp.status_code == 404


def test_semantic_get_404_when_missing():
    from aryx.api.semantic_api import semantic_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(semantic_router, "aryx.api.semantic_api",
                   SemanticStore=store_cls).get("/semantic/ds1")
    assert resp.status_code == 404


def test_dashboard_model_workspace_null_when_missing():
    from aryx.api.dashboard_model_api import dashboard_model_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(dashboard_model_router, "aryx.api.dashboard_model_api",
                   DashboardModelStore=store_cls).get("/dashboard-model/workspace")
    assert resp.status_code == 200 and resp.json() is None


def test_dashboard_model_versions_requires_dataset_id():
    from aryx.api.dashboard_model_api import dashboard_model_router
    resp = _client(dashboard_model_router, "aryx.api.dashboard_model_api").get(
        "/dashboard-model/versions")
    assert resp.status_code == 422


def test_render_telemetry_list_empty():
    from aryx.api.render_telemetry_api import render_telemetry_router
    store_cls = MagicMock()
    store_cls.return_value.list.return_value = []
    resp = _client(render_telemetry_router, "aryx.api.render_telemetry_api",
                   RenderTelemetryStore=store_cls).get(
        "/render-telemetry/list", params={"dashboard_model_id": "m1"})
    assert resp.status_code == 200 and resp.json() == []


# ── datasource_api: plain-dict responses, no Pydantic model construction ──

def test_datasource_kinds():
    from aryx.api.datasource_api import datasource_router
    resp = _client(datasource_router, "aryx.api.datasource_api").get(
        "/admin/datasources/kinds")
    assert resp.status_code == 200
    assert "kinds" in resp.json()


def test_datasource_list_flags_context_missing():
    from aryx.api.datasource_api import datasource_router
    store_cls = MagicMock()
    store_cls.return_value.list.return_value = [
        {"id": 1, "config": {}}, {"id": 2, "config": {"extra_context": "billing data"}},
    ]
    resp = _client(datasource_router, "aryx.api.datasource_api",
                   DatasourceStore=store_cls).get("/admin/datasources")
    rows = resp.json()
    assert rows[0]["context_missing"] is True
    assert rows[1]["context_missing"] is False


def test_datasource_add_requires_extra_context():
    from aryx.api.datasource_api import datasource_router
    resp = _client(datasource_router, "aryx.api.datasource_api").post(
        "/admin/datasources", json={
            "name": "db1", "kind": "postgres", "config": {}, "secret": "x",
        })
    assert resp.status_code == 400


def test_datasource_add_succeeds_with_context():
    from aryx.api.datasource_api import datasource_router
    store_cls = MagicMock()
    store_cls.return_value.add.return_value = {"id": 1, "name": "db1"}
    resp = _client(datasource_router, "aryx.api.datasource_api",
                   DatasourceStore=store_cls).post("/admin/datasources", json={
        "name": "db1", "kind": "postgres",
        "config": {"extra_context": "billing data"}, "secret": "x",
    })
    assert resp.status_code == 200 and resp.json()["id"] == 1


def test_datasource_test_404_when_missing():
    from aryx.api.datasource_api import datasource_router
    store_cls = MagicMock()
    store_cls.return_value.get.return_value = None
    resp = _client(datasource_router, "aryx.api.datasource_api",
                   DatasourceStore=store_cls).post("/admin/datasources/1/test")
    assert resp.status_code == 404


# ── andie_planner_api: the most logic-bearing router (draft_delta's two
# early-return "nothing to extend" branches are real edge cases worth
# covering, not just plumbing) ──

def test_andie_planner_get_result_404_when_missing():
    from aryx.api.andie_planner_api import andie_planner_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(andie_planner_router, "aryx.api.andie_planner_api",
                   DashboardSpecStore=store_cls).get("/andie-planner/ds1")
    assert resp.status_code == 404


def test_andie_planner_get_workspace_result_404_when_missing():
    from aryx.api.andie_planner_api import andie_planner_router
    store_cls = MagicMock()
    store_cls.return_value.latest.return_value = None
    resp = _client(andie_planner_router, "aryx.api.andie_planner_api",
                   DashboardSpecStore=store_cls).get("/andie-planner/workspace")
    assert resp.status_code == 404


def test_andie_planner_versions_empty():
    from aryx.api.andie_planner_api import andie_planner_router
    store_cls = MagicMock()
    store_cls.return_value.list.return_value = []
    resp = _client(andie_planner_router, "aryx.api.andie_planner_api",
                   DashboardSpecStore=store_cls).get("/andie-planner/versions")
    assert resp.status_code == 200 and resp.json() == []


def test_andie_planner_run_delegates_to_run_planner():
    from aryx.api.andie_planner_api import andie_planner_router
    from aryx.andie_planner.models import PlannerResult
    fake_result = PlannerResult(status="valid")
    resp = _client(andie_planner_router, "aryx.api.andie_planner_api",
                   run_planner=MagicMock(return_value=fake_result)).post(
        "/andie-planner/run", json={"dataset_id": "ds1"})
    assert resp.status_code == 200 and resp.json()["status"] == "valid"


def test_andie_planner_draft_controlled_error_when_no_approved_spec():
    from aryx.api.andie_planner_api import andie_planner_router
    spec_store_cls = MagicMock()
    spec_store_cls.return_value.latest.return_value = None
    resp = _client(andie_planner_router, "aryx.api.andie_planner_api",
                   DashboardSpecStore=spec_store_cls).post(
        "/andie-planner/delta/draft", json={"dataset_id": "ds1", "request_text": "add a chart"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "controlled_error" and body["error_code"] == "no_approved_spec"


def test_andie_planner_draft_controlled_error_when_no_planning_context():
    from aryx.api.andie_planner_api import andie_planner_router
    spec_store_cls = MagicMock()
    latest_result = MagicMock()
    latest_result.spec = MagicMock()
    spec_store_cls.return_value.latest.return_value = latest_result
    context_store_cls = MagicMock()
    context_store_cls.return_value.latest.return_value = None
    resp = _client(andie_planner_router, "aryx.api.andie_planner_api",
                   DashboardSpecStore=spec_store_cls, ContextStore=context_store_cls).post(
        "/andie-planner/delta/draft", json={"dataset_id": "ds1", "request_text": "add a chart"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "controlled_error" and body["error_code"] == "no_planning_context"


def test_andie_planner_confirm_delegates_to_confirm_delta():
    from aryx.api.andie_planner_api import andie_planner_router
    from aryx.andie_planner.models import PlannerResult
    fake_result = PlannerResult(status="valid")
    resp = _client(andie_planner_router, "aryx.api.andie_planner_api",
                   confirm_delta=MagicMock(return_value=fake_result)).post(
        "/andie-planner/delta/confirm", json={"dataset_id": "ds1"})
    assert resp.status_code == 200 and resp.json()["status"] == "valid"


# ── pipeline_link_api: explicit post-ingest entity linking ─────────────

def test_link_entities_delegates_to_link_entities_and_returns_counts():
    from aryx.api.pipeline_link_api import pipeline_link_router
    resp = _client(pipeline_link_router, "aryx.api.pipeline_link_api",
                   link_entities=MagicMock(return_value={"relationships": 12, "entities": 5})).post(
        "/pipeline/link-entities", json={"fk_links": [
            {"source_type": "Contract", "source_attr": "customer_id",
             "target_type": "Customer", "target_attr": "id", "name": "belongs_to"},
        ]})
    assert resp.status_code == 200
    assert resp.json() == {"relationships": 12, "entities": 5}


def test_link_entities_zero_matches_is_not_hidden():
    from aryx.api.pipeline_link_api import pipeline_link_router
    resp = _client(pipeline_link_router, "aryx.api.pipeline_link_api",
                   link_entities=MagicMock(return_value={"relationships": 0})).post(
        "/pipeline/link-entities", json={"fk_links": [
            {"source_type": "Contract", "source_attr": "customer_id",
             "target_type": "Customer", "target_attr": "id", "name": "belongs_to"},
        ]})
    assert resp.status_code == 200 and resp.json()["relationships"] == 0


# ── pipeline_derive_api: derive a new type by deduplicating a column ───

def test_derive_entities_delegates_and_returns_counts():
    from aryx.api.pipeline_derive_api import pipeline_derive_router
    resp = _client(pipeline_derive_router, "aryx.api.pipeline_derive_api",
                   derive_entities_by_column=MagicMock(
                       return_value={"type": "Customer", "created": 812,
                                     "source_groups": 812, "skipped_missing_key": 3})).post(
        "/pipeline/derive-entities", json={
            "source_type": "ContractLineItem", "group_by_attr": "Customer Number",
            "new_type_name": "Customer", "carry_attrs": ["Customer Name"],
        })
    assert resp.status_code == 200
    assert resp.json()["created"] == 812


def test_derive_entities_zero_created_is_not_hidden():
    from aryx.api.pipeline_derive_api import pipeline_derive_router
    resp = _client(pipeline_derive_router, "aryx.api.pipeline_derive_api",
                   derive_entities_by_column=MagicMock(
                       return_value={"type": "Customer", "created": 0,
                                     "source_groups": 0, "skipped_missing_key": 5406})).post(
        "/pipeline/derive-entities", json={
            "source_type": "ContractLineItem", "group_by_attr": "nonexistent_col",
            "new_type_name": "Customer", "carry_attrs": [],
        })
    assert resp.status_code == 200 and resp.json()["created"] == 0


def test_datasource_delete():
    from aryx.api.datasource_api import datasource_router
    store_cls = MagicMock()
    resp = _client(datasource_router, "aryx.api.datasource_api",
                   DatasourceStore=store_cls).delete("/admin/datasources/1")
    assert resp.status_code == 200 and resp.json()["status"] == "deleted"
    store_cls.return_value.delete.assert_called_once_with(1)
