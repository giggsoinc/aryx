"""Tests for the Andie Jr Planning Orchestrator (C08) — no live LLM required.

ground.py is pure/deterministic and tested directly with hand-built raw JSON
(valid, invented-column, invented-chart-type, dangling-ref, unsupported-op).
generate.py's retry/controlled-error state machine is tested by injecting a
fake complete_json_fn — no network, no real model.
"""
from __future__ import annotations

from types import SimpleNamespace

from aryx.andie_planner.generate import assemble_spec, assemble_workspace_spec
from aryx.andie_planner.ground import ground_spec
from aryx.andie_planner.models import PlannerResult
from aryx.andie_planner.prompt import PROMPT_VERSION, build_planner_prompt

APPROVED_COLUMNS = [
    {"name": "contract_id", "type": "identifier"},
    {"name": "region", "type": "categorical"},
    {"name": "contract_value", "type": "numeric"},
    {"name": "renewal_status", "type": "categorical"},
]
APPROVED_OPS = ["count", "sum", "ratio", "group_by"]
APPROVED_CHARTS = ["kpi_card", "bar"]

GOOD_RAW = {
    "business_questions": [
        {"question_id": "bq_001", "text": "What is the renewal rate?"},
        {"question_id": "bq_002", "text": "Which regions renew least?"},
        {"question_id": "bq_003", "text": "What is the renewed contract value?"},
    ],
    "kpis": [
        {
            "kpi_id": "kpi_renewal_rate", "name": "Renewal Rate",
            "source_columns": ["renewal_status", "contract_id"], "operation": "ratio",
            "numerator": {"operation": "count",
                          "filter": {"column": "renewal_status", "operator": "equals",
                                    "value": "Renewed"}},
            "denominator": {"operation": "count",
                            "filter": {"column": "renewal_status", "operator": "in",
                                      "values": ["Renewed", "Not Renewed"]}},
            "zero_denominator_policy": "return_null_with_warning", "format": "percentage",
        },
        {
            "kpi_id": "kpi_renewed_value", "name": "Renewed Contract Value",
            "source_columns": ["contract_value", "renewal_status"], "operation": "sum",
            "measure": "contract_value",
            "filter": {"column": "renewal_status", "operator": "equals", "value": "Renewed"},
            "format": "currency",
        },
    ],
    "analyses": [
        {"analysis_id": "analysis_renewal_by_region", "operation": "group_by",
         "group_by": ["region"], "metric": "kpi_renewal_rate", "sort": "ascending"},
    ],
    "visualizations": [
        {"chart_id": "chart_renewal_rate", "chart_type": "kpi_card", "source_ref": "kpi_renewal_rate"},
        {"chart_id": "chart_renewal_by_region", "chart_type": "bar",
         "source_ref": "analysis_renewal_by_region", "x_axis": "region", "y_axis": "renewal_rate"},
    ],
    "assumptions": [{"code": "pending_excluded", "meaning": "Pending contracts excluded."}],
    "warnings": [],
}


def _ground(raw):
    return ground_spec(
        raw, dataset_id="dataset_contracts", dataset_version="v1",
        approved_columns=APPROVED_COLUMNS, approved_operations=APPROVED_OPS,
        approved_charts=APPROVED_CHARTS,
    )


# ── prompt.py — discipline adapted from andie-jr (not its bug-triage content) ──

def test_prompt_version_bumped_for_discipline_change() -> None:
    assert PROMPT_VERSION == "1.1"


def test_system_prompt_carries_andie_jr_adapted_discipline() -> None:
    system, _ = build_planner_prompt(
        approved_columns=APPROVED_COLUMNS, approved_graph_paths=[],
        supported_operations=APPROVED_OPS, supported_charts=APPROVED_CHARTS,
        objective="x", target_audience="y", output_schema_version="dashboard_spec_v1",
    )
    # Minimum-facts-only (andie-jr: "extract the minimum facts needed").
    assert "do not add, assume, or infer" in system
    # Binary grounded? self-check per item (andie-jr: "Fix clear? yes/no").
    assert "explicitly present in the approved resources" in system
    # State uncertainty rather than guess (andie-jr: "state uncertainty if any").
    assert "rather than guessing" in system
    # Always include rationale (andie-jr: "education is always included").
    assert "assumptions" in system and "rationale is incomplete" in system
    # No fluff (andie-jr: "No fluff. Get to the point.").
    assert "no preamble" in system
    # The bug-triage-specific machinery must NOT leak into a generation prompt.
    for leftover in ("Debug Lead", "Affected Dev", "commit suggestion", "root cause"):
        assert leftover not in system


# ── ground.py — pure, deterministic ─────────────────────────────────────

def test_spec_example_grounds_cleanly() -> None:
    spec = _ground(GOOD_RAW)
    assert spec.spec_status == "valid"
    assert spec.spec_id == "dashboard_spec_dataset_contracts_v1"
    assert len(spec.business_questions) == 3
    assert {k.kpi_id for k in spec.kpis} == {"kpi_renewal_rate", "kpi_renewed_value"}
    assert spec.analyses[0].metric == "kpi_renewal_rate"
    assert {v.chart_id for v in spec.visualizations} == {"chart_renewal_rate", "chart_renewal_by_region"}
    assert spec.warnings == []


def test_never_computes_or_claims_a_value() -> None:
    # The spec's own counter-example: Andie must never emit a computed KPI
    # value (e.g. 0.6206) or a causal claim. Assert the model has no such
    # field at all — the guarantee is structural, not just "didn't happen to".
    spec = _ground(GOOD_RAW)
    for kpi in spec.kpis:
        assert not hasattr(kpi, "value")
        assert not hasattr(kpi, "result")
        assert not hasattr(kpi, "computed_value")
    assert not hasattr(spec, "claim") and not hasattr(spec, "insight")
    # Even if an adversarial LLM injects a fake numeric "value" key, the
    # grounded Kpi model has no slot for it — Pydantic simply drops it.
    poisoned = dict(GOOD_RAW)
    poisoned["kpis"] = [dict(GOOD_RAW["kpis"][0], value=0.6206,
                            claim="West underperforms because managers are ineffective")]
    poisoned_spec = _ground(poisoned)
    dumped = poisoned_spec.kpis[0].model_dump()
    assert "value" not in dumped and "claim" not in dumped


def test_invented_column_stripped_not_substituted() -> None:
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [{"kpi_id": "kpi_bad", "operation": "sum",
                  "source_columns": ["ghost_column"], "measure": "ghost_column"}],
    }
    spec = _ground(raw)
    assert spec.kpis[0].source_columns == []
    assert spec.kpis[0].measure is None
    assert any(w.code == "unapproved_column" for w in spec.warnings)


def test_unsupported_operation_drops_the_kpi() -> None:
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [{"kpi_id": "kpi_bad", "operation": "regress", "source_columns": ["contract_value"]}],
    }
    spec = _ground(raw)
    assert spec.kpis == []
    assert any(w.code == "unsupported_operation" for w in spec.warnings)


def test_unsupported_chart_type_dropped() -> None:
    raw = dict(GOOD_RAW, visualizations=[
        {"chart_id": "c1", "chart_type": "3d_globe", "source_ref": "kpi_renewal_rate"},
    ])
    spec = _ground(raw)
    assert spec.visualizations == []
    assert any(w.code == "unsupported_chart_type" for w in spec.warnings)


def test_dangling_source_ref_dropped() -> None:
    raw = dict(GOOD_RAW, visualizations=[
        {"chart_id": "c1", "chart_type": "bar", "source_ref": "kpi_does_not_exist"},
    ])
    spec = _ground(raw)
    assert spec.visualizations == []
    assert any(w.code == "dangling_reference" for w in spec.warnings)


def test_dangling_metric_reference_on_analysis() -> None:
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [],
        "analyses": [{"analysis_id": "a1", "operation": "group_by",
                      "group_by": ["region"], "metric": "kpi_ghost"}],
    }
    spec = _ground(raw)
    assert spec.analyses[0].metric is None
    assert any(w.code == "dangling_reference" for w in spec.warnings)


# ── workspace-scope grounding — datasets param, collision-safe ─────────

# Two datasets that BOTH have a column literally named 'model' and
# 'fields.item_id' — the real collision shape verified in production data
# (18/21 datasets in one workspace shared a column named 'model').
WORKSPACE_DATASETS = [
    {"dataset_id": "dataset_item", "approved_columns": [
        {"name": "model", "type": "categorical"},
        {"name": "fields.item_id", "type": "identifier"},
        {"name": "fields.cost", "type": "numeric"},
    ]},
    {"dataset_id": "dataset_demand", "approved_columns": [
        {"name": "model", "type": "categorical"},
        {"name": "fields.item_id", "type": "identifier"},
        {"name": "fields.quantity", "type": "numeric"},
    ]},
]


def _ground_ws(raw):
    return ground_spec(
        raw, dataset_id="workspace_1", dataset_version="v1",
        approved_columns=[], approved_operations=APPROVED_OPS,
        approved_charts=APPROVED_CHARTS, datasets=WORKSPACE_DATASETS,
    )


def test_workspace_kpi_grounds_against_its_own_dataset_only() -> None:
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [{"kpi_id": "kpi_cost", "operation": "sum", "dataset_id": "dataset_item",
                 "source_columns": ["fields.cost"]}],
    }
    spec = _ground_ws(raw)
    assert spec.kpis[0].dataset_id == "dataset_item"
    assert spec.kpis[0].source_columns == ["fields.cost"]
    assert spec.warnings == []


def test_workspace_kpi_cannot_borrow_column_from_wrong_dataset() -> None:
    # 'fields.quantity' only exists in dataset_demand, not dataset_item — the
    # collision-safety guarantee: declaring the wrong dataset_id must reject
    # the column even though the NAME 'model'/'fields.item_id' would pass in
    # either dataset (proving grounding checks the declared dataset, not just
    # "does this name exist somewhere in the workspace").
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [{"kpi_id": "kpi_bad", "operation": "sum", "dataset_id": "dataset_item",
                 "source_columns": ["fields.quantity"]}],
    }
    spec = _ground_ws(raw)
    assert spec.kpis[0].source_columns == []
    assert any(w.code == "unapproved_column" for w in spec.warnings)


def test_workspace_kpi_missing_dataset_id_is_dropped_not_guessed() -> None:
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [{"kpi_id": "kpi_ambiguous", "operation": "sum",
                 "source_columns": ["model"]}],  # no dataset_id — ambiguous
    }
    spec = _ground_ws(raw)
    assert spec.kpis == []
    assert any(w.code == "unknown_dataset" for w in spec.warnings)


def test_workspace_kpi_unknown_dataset_id_rejected() -> None:
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [{"kpi_id": "kpi_x", "operation": "sum", "dataset_id": "dataset_ghost",
                 "source_columns": ["model"]}],
    }
    spec = _ground_ws(raw)
    assert spec.kpis == []
    assert any(w.code == "unknown_dataset" for w in spec.warnings)


def test_workspace_analysis_scoped_to_its_own_dataset() -> None:
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [{"kpi_id": "kpi_cost", "operation": "sum", "dataset_id": "dataset_item",
                 "source_columns": ["fields.cost"]}],
        "analyses": [{"analysis_id": "a1", "operation": "group_by",
                      "dataset_id": "dataset_item", "group_by": ["model"],
                      "metric": "kpi_cost"}],
    }
    spec = _ground_ws(raw)
    assert spec.analyses[0].dataset_id == "dataset_item"
    assert spec.analyses[0].group_by == ["model"]
    assert spec.analyses[0].metric == "kpi_cost"


def test_workspace_visualization_can_reference_any_datasets_kpi() -> None:
    # Visualizations don't carry their own dataset_id — they reference a
    # kpi_id/analysis_id, which is already dataset-scoped by construction.
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [
            {"kpi_id": "kpi_cost", "operation": "sum", "dataset_id": "dataset_item",
             "source_columns": ["fields.cost"]},
            {"kpi_id": "kpi_qty", "operation": "sum", "dataset_id": "dataset_demand",
             "source_columns": ["fields.quantity"]},
        ],
        "visualizations": [
            {"chart_id": "c1", "chart_type": "kpi_card", "source_ref": "kpi_cost"},
            {"chart_id": "c2", "chart_type": "kpi_card", "source_ref": "kpi_qty"},
        ],
    }
    spec = _ground_ws(raw)
    assert {v.source_ref for v in spec.visualizations} == {"kpi_cost", "kpi_qty"}


def test_single_dataset_mode_unaffected_when_datasets_param_omitted() -> None:
    # Regression guard: the legacy call shape (no `datasets` arg at all) must
    # behave exactly as before — this is what proves the extension is
    # additive, not a rewrite of existing behavior. dataset_id is now
    # populated with the target dataset (better provenance) instead of blank.
    spec = _ground(GOOD_RAW)
    assert spec.spec_status == "valid"
    assert all(k.dataset_id == "dataset_contracts" for k in spec.kpis)


def test_empty_or_missing_keys_is_invalid() -> None:
    spec = _ground({})
    assert spec.spec_status == "invalid"
    assert spec.business_questions == [] and spec.kpis == []


def test_wrong_json_type_never_crashes_grounding() -> None:
    # Reproduces a real bug found via the live-model smoke test: a small local
    # model returned zero_denominator_policy=false (a bool) instead of a
    # policy string. Wrong-typed fields must be dropped + warned, never crash.
    raw = {
        "business_questions": GOOD_RAW["business_questions"],
        "kpis": [{
            "kpi_id": "kpi_x", "name": 123, "operation": "ratio",
            "source_columns": ["contract_value"],
            "zero_denominator_policy": False, "format": True,
        }],
        "analyses": [{"analysis_id": "a1", "operation": "group_by",
                      "group_by": ["region"], "sort": 42}],
        "visualizations": [{"chart_id": 7, "chart_type": "bar", "source_ref": "kpi_x"}],
    }
    spec = _ground(raw)                      # must not raise
    kpi = spec.kpis[0]
    assert kpi.zero_denominator_policy is None
    assert kpi.format == "number"             # bad type -> default, not crash
    assert kpi.name == "kpi_x"                # bad type -> falls back to kpi_id
    assert any(w.code == "bad_field_type" for w in spec.warnings)
    assert spec.analyses[0].sort is None


def test_wrong_json_type_end_to_end_is_never_a_crash() -> None:
    # Same malformed shape, but through the full assemble_spec path (fake
    # LLM) — must resolve to a PlannerResult, never raise.
    def fake_complete_json(broker, tier, system, user, schema):
        return {
            "business_questions": GOOD_RAW["business_questions"],
            "kpis": [{"kpi_id": "kpi_x", "operation": "sum",
                     "source_columns": ["contract_value"],
                     "zero_denominator_policy": False}],
        }

    result = assemble_spec(_ctx(), objective="x", broker=_FakeBroker(),
                           complete_json_fn=fake_complete_json)
    assert isinstance(result, PlannerResult)
    assert result.status in ("valid", "invalid")   # resolved, not an exception
    assert result.spec is not None
    assert result.spec.kpis[0].zero_denominator_policy is None


def test_question_count_out_of_range_warns() -> None:
    raw = dict(GOOD_RAW, business_questions=[{"question_id": "bq_1", "text": "only one?"}])
    spec = _ground(raw)
    assert any(w.code == "question_count_out_of_range" for w in spec.warnings)


# ── generate.py — retry / controlled-error state machine (fake LLM) ────

class _FakeBroker:
    def choose(self, tier):
        return SimpleNamespace(name="fake-model")


def _ctx():
    return SimpleNamespace(
        dataset_id="dataset_contracts", dataset_version="v1", domain="contract_management",
        approved_columns=[SimpleNamespace(name=c["name"], type=c["type"]) for c in APPROVED_COLUMNS],
        approved_graph_paths=["path_contract_manager_region"],
        supported_operations=APPROVED_OPS, supported_charts=APPROVED_CHARTS,
    )


def test_default_prompt_version_tracks_prompt_module() -> None:
    # Regression: generate.py used to hardcode its own "1.0" independent of
    # prompt.py's PROMPT_VERSION, so a bumped prompt never showed up in the
    # persisted spec's provenance. The default must track the real constant.
    def fake_complete_json(broker, tier, system, user, schema):
        return GOOD_RAW

    result = assemble_spec(_ctx(), objective="x", broker=_FakeBroker(),
                           complete_json_fn=fake_complete_json)
    assert result.spec.prompt_version == PROMPT_VERSION


def test_first_attempt_success() -> None:
    calls = []

    def fake_complete_json(broker, tier, system, user, schema):
        calls.append(user)
        return GOOD_RAW

    result = assemble_spec(_ctx(), objective="renewal performance", broker=_FakeBroker(),
                           complete_json_fn=fake_complete_json)
    assert result.status == "valid"
    assert result.attempts == 1
    assert len(calls) == 1


def test_malformed_first_attempt_retries_then_succeeds() -> None:
    calls = []

    def fake_complete_json(broker, tier, system, user, schema):
        calls.append(user)
        return {} if len(calls) == 1 else GOOD_RAW

    result = assemble_spec(_ctx(), objective="x", broker=_FakeBroker(),
                           complete_json_fn=fake_complete_json)
    assert result.status == "valid"
    assert result.attempts == 2
    assert len(calls) == 2
    assert "rejected" in calls[1]           # repair reminder was appended


def test_malformed_both_attempts_is_controlled_error() -> None:
    def fake_complete_json(broker, tier, system, user, schema):
        return {}

    result = assemble_spec(_ctx(), objective="x", broker=_FakeBroker(),
                           complete_json_fn=fake_complete_json)
    assert result.status == "controlled_error"
    assert result.error_code == "malformed_json"
    assert result.attempts == 2
    assert result.spec is None


def test_provider_exception_both_attempts_is_controlled_error() -> None:
    def fake_complete_json(broker, tier, system, user, schema):
        raise TimeoutError("ollama unreachable")

    result = assemble_spec(_ctx(), objective="x", broker=_FakeBroker(),
                           complete_json_fn=fake_complete_json)
    assert result.status == "controlled_error"
    assert result.error_code == "llm_call_failed"
    assert "unreachable" in result.error_message


def test_never_raises_to_caller() -> None:
    # No matter how badly the fake LLM misbehaves, the caller gets a
    # PlannerResult, never an exception.
    def fake_complete_json(broker, tier, system, user, schema):
        raise RuntimeError("boom")

    result = assemble_spec(_ctx(), objective="x", broker=_FakeBroker(),
                           complete_json_fn=fake_complete_json)
    assert isinstance(result, PlannerResult)
    assert result.status == "controlled_error"


# ── assemble_workspace_spec — retry state machine, workspace scope ─────

def _workspace_ctx():
    return SimpleNamespace(
        dataset_id="workspace_1", dataset_version="v1", domain="mixed",
        datasets=[
            SimpleNamespace(dataset_id="dataset_item", dataset_version="v1",
                            approved_columns=[SimpleNamespace(name="fields.cost", type="numeric")]),
            SimpleNamespace(dataset_id="dataset_demand", dataset_version="v1",
                            approved_columns=[SimpleNamespace(name="fields.quantity", type="numeric")]),
        ],
        approved_graph_paths=["path_item_demand"],
        supported_operations=APPROVED_OPS, supported_charts=APPROVED_CHARTS,
    )


WORKSPACE_GOOD_RAW = {
    "business_questions": GOOD_RAW["business_questions"],
    "kpis": [
        {"kpi_id": "kpi_cost", "operation": "sum", "dataset_id": "dataset_item",
         "source_columns": ["fields.cost"]},
        {"kpi_id": "kpi_qty", "operation": "sum", "dataset_id": "dataset_demand",
         "source_columns": ["fields.quantity"]},
    ],
}


def test_workspace_spec_first_attempt_success() -> None:
    def fake_complete_json(broker, tier, system, user, schema):
        return WORKSPACE_GOOD_RAW

    result = assemble_workspace_spec(_workspace_ctx(), objective="cross-dataset view",
                                     broker=_FakeBroker(), complete_json_fn=fake_complete_json)
    assert result.status == "valid"
    assert {k.dataset_id for k in result.spec.kpis} == {"dataset_item", "dataset_demand"}


def test_workspace_spec_malformed_retries_then_succeeds() -> None:
    calls = []

    def fake_complete_json(broker, tier, system, user, schema):
        calls.append(user)
        return {} if len(calls) == 1 else WORKSPACE_GOOD_RAW

    result = assemble_workspace_spec(_workspace_ctx(), objective="x", broker=_FakeBroker(),
                                     complete_json_fn=fake_complete_json)
    assert result.status == "valid"
    assert result.attempts == 2


def test_workspace_spec_never_raises_on_provider_failure() -> None:
    def fake_complete_json(broker, tier, system, user, schema):
        raise TimeoutError("ollama unreachable")

    result = assemble_workspace_spec(_workspace_ctx(), objective="x", broker=_FakeBroker(),
                                     complete_json_fn=fake_complete_json)
    assert isinstance(result, PlannerResult)
    assert result.status == "controlled_error"
    assert result.error_code == "llm_call_failed"


def test_workspace_spec_prompt_mentions_multiple_datasets() -> None:
    from aryx.andie_planner.prompt import build_workspace_planner_prompt
    _, user = build_workspace_planner_prompt(
        datasets=[{"dataset_id": "dataset_item", "approved_columns": []},
                 {"dataset_id": "dataset_demand", "approved_columns": []}],
        approved_graph_paths=[], supported_operations=APPROVED_OPS,
        supported_charts=APPROVED_CHARTS, objective="x", target_audience="y",
        output_schema_version="dashboard_spec_v1",
    )
    assert "dataset_id" in user
    assert "MULTIPLE datasets" in user
