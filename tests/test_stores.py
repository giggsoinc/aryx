"""Direct tests for the 14 store modules added this branch — a raven-review
finding: they were only ever mocked out in the API route tests
(test_api_routes.py), never exercised themselves. Follows this codebase's
existing fake-pool convention (see test_job_store.py): a fake Cursor/
Connection/Pool records `execute()` calls and returns configured
fetchone/fetchall results, with `get_pool` monkeypatched per store module.

Coverage priority mirrors real bug risk, not exhaustiveness: the two stores
that hand-reconstruct a model from positional column order (DatasetStore,
IntentStore) get thorough field-order checks, since a reordering there
would silently corrupt every field. The JSONB-blob stores (`Model(**row[0])`)
get one round-trip check each — real regression coverage, even though the
reconstruction itself is nearly tautological — plus every store's
None-when-missing branch, since that's the one behavior every read path
must get right.
"""
from __future__ import annotations

from unittest.mock import patch

from aryx.analysis_execution.models import ExecutionRun
from aryx.andie_planner.models import PlannerResult
from aryx.dashboard_composition.models import DashboardModel
from aryx.dashboard_render.models import RenderTelemetry
from aryx.dataset.models import DatasetIngestResult
from aryx.execution_compiler.models import ExecutionPlan
from aryx.graph_intake.models import GraphIntakeResult
from aryx.graph_profiler.models import GraphProfile
from aryx.intent.models import IntentPreferences, UserIntent
from aryx.planning.models import PlanningContext
from aryx.preprocess.models import AnalysisDataset
from aryx.profiler.models import DatasetProfile
from aryx.semantic.models import SemanticProfile
from aryx.spec_validation.models import ValidationReport


class _Cursor:
    def __init__(self, fetchone=None, fetchall=None, description=None):
        self._fetchone = fetchone
        self._fetchall = fetchall or []
        self.description = description or []
        self.calls: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query, params=()):
        self.calls.append((query, params))

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def cursor(self):
        return self._cursor


class _Pool:
    def __init__(self, cursor):
        self._cursor = cursor

    def connection(self):
        return _Conn(self._cursor)


def _patched(module: str, cursor: _Cursor):
    return patch(f"{module}.get_pool", return_value=_Pool(cursor))


# ── column-order stores: real bug risk, tested thoroughly ──────────────

def test_dataset_store_row_to_result_field_order():
    from aryx.store.dataset_store import DatasetStore
    row = ("req-1", "ds1", "v1", "csv", "hash1", "ref1", 100, ["a", "b"], [],
          "accepted", "profiled", [], "file.csv", 2048, "2026-01-01T00:00:00Z")
    cursor = _Cursor(fetchone=row)
    with _patched("aryx.store.dataset_store", cursor):
        result = DatasetStore("dsn").latest("ds1")
    assert isinstance(result, DatasetIngestResult)
    assert result.request_id == "req-1" and result.dataset_id == "ds1"
    assert result.dataset_version == "v1" and result.format == "csv"
    assert result.content_hash == "hash1" and result.columns == ["a", "b"]
    assert result.ingestion_status == "accepted" and result.file_size_bytes == 2048


def test_dataset_store_latest_none_when_missing():
    from aryx.store.dataset_store import DatasetStore
    cursor = _Cursor(fetchone=None)
    with _patched("aryx.store.dataset_store", cursor):
        assert DatasetStore("dsn").latest("nope") is None


def test_dataset_store_count_versions():
    from aryx.store.dataset_store import DatasetStore
    cursor = _Cursor(fetchone=(3,))
    with _patched("aryx.store.dataset_store", cursor):
        assert DatasetStore("dsn").count_versions("ds1") == 3


def test_dataset_store_save_version_writes_bytes_to_disk_not_postgres():
    """raven-review finding: raw bytes must never reach a SQL param — only
    the content-hash-derived blob ref does."""
    import tempfile
    from unittest.mock import patch as _patch
    from aryx.dataset.models import DatasetIngestResult
    from aryx.store.dataset_store import DatasetStore

    cursor = _Cursor()
    with tempfile.TemporaryDirectory() as tmp:
        with _patched("aryx.store.dataset_store", cursor), \
             _patch("aryx.store.dataset_store.get_settings",
                    return_value=type("S", (), {"blob_dir": tmp})()):
            store = DatasetStore("dsn")
            result = DatasetIngestResult(
                request_id="req-1", dataset_id="ds1", dataset_version="v1",
                format="csv", content_hash="sha256:" + "c" * 64,
            )
            store.save_version(result, raw_bytes=b"a,b\n1,2\n")

    insert_query, insert_params = cursor.calls[0]
    assert b"a,b\n1,2\n" not in insert_params  # bytes never went into the SQL call
    assert "c" * 64 in insert_params          # the blob ref (bare hex digest) did
    assert result.raw_snapshot_ref == "c" * 64  # caller's in-memory result matches too


def test_dataset_store_get_raw_reads_bytes_back_from_disk():
    from unittest.mock import patch as _patch
    from aryx.store.blob_store import write_blob
    from aryx.store.dataset_store import DatasetStore
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ref = write_blob(tmp, "sha256:" + "d" * 64, b"raw file contents")
        cursor = _Cursor(fetchone=(ref, "csv"))
        with _patched("aryx.store.dataset_store", cursor), \
             _patch("aryx.store.dataset_store.get_settings",
                    return_value=type("S", (), {"blob_dir": tmp})()):
            raw, fmt = DatasetStore("dsn").get_raw("ds1", "v1")
    assert raw == b"raw file contents"
    assert fmt == "csv"


def test_intent_store_row_to_intent_field_order():
    from aryx.store.intent_store import IntentStore
    row = ("req-1", "v1", "file.csv", "contracts", "analyze renewals",
          {"preferred_kpis": ["renewal_rate"]}, "valid", ["w1"], [],
          "2026-01-01T00:00:00Z")
    cursor = _Cursor(fetchone=row)
    with _patched("aryx.store.intent_store", cursor):
        result = IntentStore("dsn").get("req-1")
    assert isinstance(result, UserIntent)
    assert result.request_id == "req-1" and result.domain == "contracts"
    assert result.objective == "analyze renewals"
    assert isinstance(result.preferences, IntentPreferences)
    assert result.preferences.preferred_kpis == ["renewal_rate"]
    assert result.validation_status == "valid" and result.warnings == ["w1"]


def test_intent_store_get_none_when_missing():
    from aryx.store.intent_store import IntentStore
    cursor = _Cursor(fetchone=None)
    with _patched("aryx.store.intent_store", cursor):
        assert IntentStore("dsn").get("nope") is None


def test_intent_store_has_valid_intent():
    from aryx.store.intent_store import IntentStore
    cursor = _Cursor(fetchone=(True,))
    with _patched("aryx.store.intent_store", cursor):
        assert IntentStore("dsn").has_valid_intent() is True
    cursor2 = _Cursor(fetchone=None)
    with _patched("aryx.store.intent_store", cursor2):
        assert IntentStore("dsn").has_valid_intent() is False


# ── JSONB-blob stores: save() reaches the DB, latest()/list() round-trip,
# None-when-missing on every read path ──────────────────────────────────

def test_context_store_roundtrip_and_missing():
    from aryx.store.context_store import ContextStore
    ctx = PlanningContext(planning_context_id="pc1", dataset_id="ds1", dataset_version="v1")
    cursor = _Cursor(fetchone=(ctx.model_dump(mode="json"),))
    with _patched("aryx.store.context_store", cursor):
        got = ContextStore("dsn").latest("ds1")
    assert got is not None and got.planning_context_id == "pc1"
    with _patched("aryx.store.context_store", _Cursor(fetchone=None)):
        assert ContextStore("dsn").latest("ds1") is None


def test_context_store_save_hits_the_db():
    from aryx.store.context_store import ContextStore
    ctx = PlanningContext(planning_context_id="pc1", dataset_id="ds1", dataset_version="v1")
    cursor = _Cursor()
    with _patched("aryx.store.context_store", cursor):
        ContextStore("dsn").save(ctx)
    assert len(cursor.calls) == 1


def test_dashboard_spec_store_roundtrip_and_missing():
    from aryx.store.dashboard_spec_store import DashboardSpecStore
    result = PlannerResult(status="valid")
    cursor = _Cursor(fetchone=(result.model_dump(mode="json"),))
    with _patched("aryx.store.dashboard_spec_store", cursor):
        got = DashboardSpecStore("dsn").latest("ds1")
    assert got is not None and got.status == "valid"
    with _patched("aryx.store.dashboard_spec_store", _Cursor(fetchone=None)):
        assert DashboardSpecStore("dsn").latest("ds1") is None


def test_dashboard_spec_store_list_roundtrip():
    from aryx.store.dashboard_spec_store import DashboardSpecStore
    result = PlannerResult(status="valid")
    cursor = _Cursor(fetchall=[(result.model_dump(mode="json"),)])
    with _patched("aryx.store.dashboard_spec_store", cursor):
        got = DashboardSpecStore("dsn").list()
    assert len(got) == 1 and got[0].status == "valid"


def test_execution_plan_store_roundtrip_and_missing():
    from aryx.store.execution_plan_store import ExecutionPlanStore
    plan = ExecutionPlan(execution_plan_id="p1", spec_id="s1", dataset_id="ds1", dataset_version="v1")
    cursor = _Cursor(fetchone=(plan.model_dump(mode="json"),))
    with _patched("aryx.store.execution_plan_store", cursor):
        got = ExecutionPlanStore("dsn").latest("ds1")
    assert got is not None and got.execution_plan_id == "p1"
    with _patched("aryx.store.execution_plan_store", _Cursor(fetchone=None)):
        assert ExecutionPlanStore("dsn").latest("ds1") is None


def test_execution_run_store_roundtrip_and_missing():
    from aryx.store.execution_run_store import ExecutionRunStore
    run = ExecutionRun(execution_run_id="r1", execution_plan_id="p1", spec_id="s1",
                       dataset_id="ds1", dataset_version="v1")
    cursor = _Cursor(fetchone=(run.model_dump(mode="json"),))
    with _patched("aryx.store.execution_run_store", cursor):
        got = ExecutionRunStore("dsn").latest("ds1")
    assert got is not None and got.execution_run_id == "r1"
    with _patched("aryx.store.execution_run_store", _Cursor(fetchone=None)):
        assert ExecutionRunStore("dsn").latest("ds1") is None


def test_graph_intake_store_roundtrip_and_missing():
    from aryx.store.graph_intake_store import GraphIntakeStore
    result = GraphIntakeResult(graph_id="g1", graph_version="v1")
    cursor = _Cursor(fetchone=(result.model_dump(mode="json"),))
    with _patched("aryx.store.graph_intake_store", cursor):
        got = GraphIntakeStore("dsn").latest("g1")
    assert got is not None and got.graph_id == "g1"
    with _patched("aryx.store.graph_intake_store", _Cursor(fetchone=None)):
        assert GraphIntakeStore("dsn").latest("g1") is None


def test_graph_intake_store_adapter_read_bounds_and_defaults():
    from aryx.store.graph_intake_store import GraphIntakeStore
    norm = {"entities": [{"id": i} for i in range(5)], "relationships": [{"id": i} for i in range(5)]}
    cursor = _Cursor(fetchone=(norm,))
    with _patched("aryx.store.graph_intake_store", cursor):
        got = GraphIntakeStore("dsn").adapter_read("g1", limit=2)
    assert len(got["entities"]) == 2 and len(got["relationships"]) == 2
    with _patched("aryx.store.graph_intake_store", _Cursor(fetchone=None)):
        empty = GraphIntakeStore("dsn").adapter_read("g1")
    assert empty == {"entities": [], "relationships": []}


def test_graph_profile_store_roundtrip_and_missing():
    from aryx.store.graph_profile_store import GraphProfileStore
    profile = GraphProfile(graph_profile_id="gp1", graph_id="g1", graph_version="v1")
    cursor = _Cursor(fetchone=(profile.model_dump(mode="json"),))
    with _patched("aryx.store.graph_profile_store", cursor):
        got = GraphProfileStore("dsn").latest("g1")
    assert got is not None and got.graph_profile_id == "gp1"
    with _patched("aryx.store.graph_profile_store", _Cursor(fetchone=None)):
        assert GraphProfileStore("dsn").latest("g1") is None


def test_semantic_store_roundtrip_and_missing():
    from aryx.store.semantic_store import SemanticStore
    profile = SemanticProfile(semantic_profile_id="sp1", dataset_id="ds1", dataset_version="v1")
    cursor = _Cursor(fetchone=(profile.model_dump(mode="json"),))
    with _patched("aryx.store.semantic_store", cursor):
        got = SemanticStore("dsn").latest("ds1")
    assert got is not None and got.semantic_profile_id == "sp1"
    with _patched("aryx.store.semantic_store", _Cursor(fetchone=None)):
        assert SemanticStore("dsn").latest("ds1") is None


def test_profile_store_roundtrip_and_missing():
    from aryx.store.profile_store import ProfileStore
    profile = DatasetProfile(dataset_profile_id="dp1", dataset_id="ds1", dataset_version="v1")
    cursor = _Cursor(fetchone=(profile.model_dump(mode="json"),))
    with _patched("aryx.store.profile_store", cursor):
        got = ProfileStore("dsn").latest("ds1")
    assert got is not None and got.dataset_profile_id == "dp1"
    with _patched("aryx.store.profile_store", _Cursor(fetchone=None)):
        assert ProfileStore("dsn").latest("ds1") is None


def test_analysis_dataset_store_roundtrip_and_missing():
    from aryx.store.analysis_dataset_store import AnalysisDatasetStore
    ad = AnalysisDataset(analysis_dataset_id="ad1", source_dataset_id="ds1", source_dataset_version="v1")
    cursor = _Cursor(fetchone=(ad.model_dump(mode="json"),))
    with _patched("aryx.store.analysis_dataset_store", cursor):
        got = AnalysisDatasetStore("dsn").latest("ds1")
    assert got is not None and got.analysis_dataset_id == "ad1"
    with _patched("aryx.store.analysis_dataset_store", _Cursor(fetchone=None)):
        assert AnalysisDatasetStore("dsn").latest("ds1") is None


def test_dashboard_model_store_roundtrip_and_missing():
    from aryx.store.dashboard_model_store import DashboardModelStore
    model = DashboardModel(dashboard_model_id="dm1", spec_id="s1", dataset_id="ds1", dataset_version="v1")
    cursor = _Cursor(fetchone=(model.model_dump(mode="json"),))
    with _patched("aryx.store.dashboard_model_store", cursor):
        got = DashboardModelStore("dsn").latest("ds1")
    assert got is not None and got.dashboard_model_id == "dm1"
    with _patched("aryx.store.dashboard_model_store", _Cursor(fetchone=None)):
        assert DashboardModelStore("dsn").latest("ds1") is None


def test_spec_validation_store_roundtrip_and_missing():
    from aryx.store.spec_validation_store import SpecValidationStore
    report = ValidationReport(validation_id="v1", status="approved")
    cursor = _Cursor(fetchone=(report.model_dump(mode="json"),))
    with _patched("aryx.store.spec_validation_store", cursor):
        got = SpecValidationStore("dsn").latest("v1")
    assert got is not None and got.status == "approved"
    with _patched("aryx.store.spec_validation_store", _Cursor(fetchone=None)):
        assert SpecValidationStore("dsn").latest("v1") is None


def test_spec_validation_store_count_attempts():
    from aryx.store.spec_validation_store import SpecValidationStore
    cursor = _Cursor(fetchone=(2,))
    with _patched("aryx.store.spec_validation_store", cursor):
        assert SpecValidationStore("dsn").count_attempts("v1") == 2


def test_render_telemetry_store_list_uses_cursor_description():
    from aryx.store.render_telemetry_store import RenderTelemetryStore

    class _Col:
        def __init__(self, name):
            self.name = name

    cursor = _Cursor(
        fetchall=[("r1", "m1", "success", 5, 0)],
        description=[_Col(n) for n in ("render_id", "dashboard_model_id", "render_status",
                                       "rendered_component_count", "warning_count")],
    )
    with _patched("aryx.store.render_telemetry_store", cursor):
        rows = RenderTelemetryStore("dsn").list("m1")
    assert rows == [{"render_id": "r1", "dashboard_model_id": "m1", "render_status": "success",
                     "rendered_component_count": 5, "warning_count": 0}]


def test_ontology_store_merge_attributes_keeps_prior_and_dedupes():
    from aryx.store.ontology_store import OntologyStore
    row = ("Customer", ["Customer Number", "Customer name"], "approved", "manual", None)
    cursor = _Cursor(fetchall=[row])
    with _patched("aryx.store.ontology_store", cursor):
        OntologyStore("dsn", 29).merge_attributes(
            "Customer", ["Customer Number", "Customer Name"])
    _, upsert_params = cursor.calls[-1]
    merged_attrs = upsert_params[2].obj  # psycopg.types.json.Json wrapper
    assert merged_attrs == ["Customer Number", "Customer name", "Customer Name"]


def test_ontology_store_merge_attributes_creates_when_type_is_new():
    from aryx.store.ontology_store import OntologyStore
    cursor = _Cursor(fetchall=[])
    with _patched("aryx.store.ontology_store", cursor):
        OntologyStore("dsn", 29).merge_attributes("Contract", ["contract_number", "status"])
    _, upsert_params = cursor.calls[-1]
    assert upsert_params[2].obj == ["contract_number", "status"]
    assert upsert_params[3] == "approved"  # caller's default applies only on create
    assert upsert_params[4] == "derived"


def test_ontology_store_merge_attributes_never_overwrites_existing_status_or_source():
    """A derive run merging attrs into an existing type must not silently flip
    it to approved/derived — that would bypass the HITL approve_type gate or
    clobber a manually-sourced type's provenance."""
    from aryx.store.ontology_store import OntologyStore
    row = ("Customer", ["Customer Number"], "proposed", "manual", None)
    cursor = _Cursor(fetchall=[row])
    with _patched("aryx.store.ontology_store", cursor):
        OntologyStore("dsn", 29).merge_attributes("Customer", ["Segment"])
    _, upsert_params = cursor.calls[-1]
    assert upsert_params[2].obj == ["Customer Number", "Segment"]
    assert upsert_params[3] == "proposed"
    assert upsert_params[4] == "manual"


def test_render_telemetry_store_save_hits_the_db():
    from aryx.store.render_telemetry_store import RenderTelemetryStore
    telemetry = RenderTelemetry(render_id="r1", dashboard_model_id="m1")
    cursor = _Cursor()
    with _patched("aryx.store.render_telemetry_store", cursor):
        RenderTelemetryStore("dsn").save(telemetry)
    assert len(cursor.calls) == 1
