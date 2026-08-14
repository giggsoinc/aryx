"""Tests for Preprocessing and Transformation (C10) — no DB, no LLM.

policy.py/transform.py are pure and tested directly. run.py's DB-touching glue
(DatasetStore, AnalysisDatasetStore) is exercised with those two classes
mocked — no real Postgres needed, matching the C09 test discipline.
"""
from __future__ import annotations

from unittest.mock import patch

from aryx.andie_planner.ground import ground_spec
from aryx.preprocess.policy import derive_conversion_policy, derive_null_policy, referenced_columns
from aryx.preprocess.run import run_preprocess
from aryx.preprocess.transform import THRESHOLD, convert_column
from aryx.profiler.models import ColumnProfile, DatasetProfile
from aryx.profiler.profile import profile_dataset

APPROVED_COLUMNS = [
    {"name": "contract_id", "type": "identifier"},
    {"name": "region", "type": "categorical"},
    {"name": "contract_value", "type": "numeric"},
    {"name": "renewal_status", "type": "categorical"},
]
APPROVED_OPS = ["count", "sum", "ratio", "group_by"]
APPROVED_CHARTS = ["kpi_card", "bar"]

RAW = {
    "business_questions": [
        {"question_id": "bq_001", "text": "What is the renewal rate?"},
        {"question_id": "bq_002", "text": "Which regions renew least?"},
        {"question_id": "bq_003", "text": "What is the renewed contract value?"},
    ],
    "kpis": [
        {
            "kpi_id": "kpi_value", "name": "Renewed Value", "operation": "sum",
            "source_columns": ["contract_value"], "measure": "contract_value",
            "filter": {"column": "renewal_status", "operator": "equals", "value": "Renewed"},
        },
    ],
    "analyses": [
        {"analysis_id": "a1", "operation": "group_by", "group_by": ["region"], "metric": "kpi_value"},
    ],
}


def _ground():
    return ground_spec(
        RAW, dataset_id="dataset_contracts", dataset_version="v1",
        approved_columns=APPROVED_COLUMNS, approved_operations=APPROVED_OPS,
        approved_charts=APPROVED_CHARTS,
    )


# ── policy.py ────────────────────────────────────────────────────────────

def test_referenced_columns_pulls_measure_filter_and_group_by() -> None:
    spec = _ground()
    cols = referenced_columns(spec, "dataset_contracts")
    assert cols == {"contract_value", "renewal_status", "region"}


def test_referenced_columns_scoped_to_declared_dataset_only() -> None:
    spec = _ground()
    assert referenced_columns(spec, "some_other_dataset") == set()


def _fake_profile(column_types: dict[str, str]) -> DatasetProfile:
    """A DatasetProfile with explicit canonical_type per column — decouples
    the policy-mapping test from C03's own evidence-based inference quirks
    on tiny samples (e.g. 2 distinct values out of 2 rows reads as 'text',
    not 'categorical', since C03 requires unique_count < row_count)."""
    return DatasetProfile(
        dataset_profile_id="profile_x_v1", dataset_id="x", dataset_version="v1",
        row_count=10, column_count=len(column_types),
        columns=[
            ColumnProfile(name=name, original_type="string", canonical_type=canonical,
                         candidate_role="attribute")
            for name, canonical in column_types.items()
        ],
    )


def test_derive_conversion_policy_maps_canonical_type() -> None:
    profile = _fake_profile({
        "contract_value": "numeric", "region": "categorical", "contract_id": "identifier",
    })
    policy = derive_conversion_policy(profile, {"contract_value", "region", "contract_id"})
    assert policy["contract_value"] == "numeric_conversion"
    assert policy["region"] == "trim_and_normalize_category"
    assert policy["contract_id"] == "trim_whitespace"


def test_derive_conversion_policy_skips_columns_not_referenced_or_not_in_profile() -> None:
    profile = _fake_profile({"contract_value": "numeric", "unrelated_col": "text"})
    policy = derive_conversion_policy(profile, {"contract_value", "ghost_column"})
    assert policy == {"contract_value": "numeric_conversion"}


def test_derive_null_policy_excludes_aggregated_measure() -> None:
    spec = _ground()
    policy = derive_null_policy(spec, {"contract_value", "region"}, "dataset_contracts")
    assert policy["contract_value"] == "exclude_from_aggregation"
    assert policy["region"] == "retain"


# ── transform.py ─────────────────────────────────────────────────────────

def test_trim_whitespace_counts_changed_not_failed() -> None:
    values, failed, changed, reverted = convert_column([" a ", "b", None], "trim_whitespace")
    assert values == ["a", "b", None]
    assert failed == 0 and changed == 1 and reverted is False


def test_numeric_conversion_clean_column() -> None:
    values, failed, changed, reverted = convert_column(["100", "$200", "1,000"], "numeric_conversion")
    assert values == [100.0, 200.0, 1000.0]
    assert failed == 0 and reverted is False


def test_numeric_conversion_clean_values_not_counted_as_changed() -> None:
    # "100" -> 100.0 is a type change only (no formatting to strip), not a
    # content repair — must not inflate the changed_rows count.
    values, failed, changed, reverted = convert_column(["100", "200", "300"], "numeric_conversion")
    assert values == [100.0, 200.0, 300.0]
    assert changed == 0


def test_numeric_conversion_formatting_cruft_counted_as_changed() -> None:
    # "$200" and "1,000" needed real cleanup (currency/comma stripped);
    # "100" did not, so only 2 of 3 rows should count as changed.
    values, failed, changed, reverted = convert_column(["100", "$200", "1,000"], "numeric_conversion")
    assert changed == 2


def test_numeric_conversion_under_threshold_keeps_converted_values() -> None:
    # 1 bad out of 20 = 5% < 10% threshold -> stays converted, failure recorded.
    values_in = ["100"] * 19 + ["oops"]
    values, failed, changed, reverted = convert_column(values_in, "numeric_conversion")
    assert failed == 1
    assert reverted is False
    assert values[-1] is None and values[0] == 100.0


def test_numeric_conversion_over_threshold_reverts_column() -> None:
    # 3 bad out of 10 = 30% > 10% threshold -> revert to original strings.
    values_in = ["100"] * 7 + ["oops", "bad", "nope"]
    values, failed, changed, reverted = convert_column(values_in, "numeric_conversion")
    assert reverted is True
    assert failed == 3
    assert values == values_in  # original (null-standardized) values kept
    assert THRESHOLD == 0.10


def test_date_conversion_clean_column() -> None:
    values, failed, changed, reverted = convert_column(
        ["2024-01-15", "2024-02-01", "2024-03-10"], "date_conversion")
    assert values == ["2024-01-15", "2024-02-01", "2024-03-10"]
    assert failed == 0 and reverted is False
    assert changed == 0  # already ISO-formatted — nothing to reformat


def test_date_conversion_reformatting_counted_as_changed() -> None:
    values, failed, changed, reverted = convert_column(
        ["2024-01-15", "2024/02/01"], "date_conversion")
    assert values == ["2024-01-15", "2024-02-01"]
    assert changed == 1  # only the slash-formatted date needed reformatting


def test_date_conversion_over_threshold_reverts() -> None:
    # 1 bad out of 2 = 50% > 10% threshold -> revert to original strings.
    values, failed, changed, reverted = convert_column(["2024-01-15", "not-a-date"], "date_conversion")
    assert failed == 1 and reverted is True
    assert values == ["2024-01-15", "not-a-date"]


def test_boolean_conversion_clean_column() -> None:
    values, failed, changed, reverted = convert_column(["yes", "no", "yes", "no"], "boolean_conversion")
    assert values == [True, False, True, False]
    assert failed == 0 and reverted is False


def test_boolean_conversion_never_counts_as_changed() -> None:
    # Encoding "yes"/"no" to a Python bool is a type mapping, not a content
    # repair — str("yes") != str(True) must not be treated as a change.
    values, failed, changed, reverted = convert_column(["yes", "no", "yes", "no"], "boolean_conversion")
    assert changed == 0


def test_boolean_conversion_over_threshold_reverts() -> None:
    # 1 bad out of 3 = 33% > 10% threshold -> revert to original strings.
    values, failed, changed, reverted = convert_column(["yes", "no", "maybe"], "boolean_conversion")
    assert failed == 1 and reverted is True
    assert values == ["yes", "no", "maybe"]


def test_category_trim_no_reordering() -> None:
    values, failed, changed, reverted = convert_column([" Renewed", "Not Renewed "], "trim_and_normalize_category")
    assert values == ["Renewed", "Not Renewed"]
    assert failed == 0


# ── run.py — mocked stores, real ground_spec + profile_dataset ───────────

def test_run_preprocess_end_to_end_with_mocked_stores() -> None:
    # Clean data throughout: C03's own canonical_type inference requires
    # every non-null value to match before it calls a column "numeric" at
    # all (same evidence-based rule C10's convert_column applies) — so a
    # column C03 actually profiled as numeric should convert with zero
    # failures by construction. The threshold/revert path is covered by the
    # convert_column unit tests above, independent of C03's own inference.
    spec = _ground()
    csv_bytes = (
        b"contract_id,region,contract_value,renewal_status\n"
        b"C1,West,100,Renewed\nC2, East ,200,Not Renewed\nC3,West,300,Renewed\n"
    )
    profile = profile_dataset(csv_bytes, "csv", "dataset_contracts", "v1")
    assert next(c for c in profile.columns if c.name == "contract_value").canonical_type == "numeric"

    saved = {}

    with patch("aryx.preprocess.run.DatasetStore") as MockDatasetStore, \
         patch("aryx.preprocess.run.AnalysisDatasetStore") as MockAnalysisStore:
        MockDatasetStore.return_value.get_raw.return_value = (csv_bytes, "csv")
        MockAnalysisStore.return_value.save.side_effect = lambda r: saved.update(result=r)

        result = run_preprocess("dsn", 1, "dataset_contracts", spec, profile)

    assert result is not None
    assert result.row_count == 3
    assert result.source_dataset_id == "dataset_contracts"
    cols_touched = {t.column for t in result.transformations}
    assert cols_touched == {"contract_value", "renewal_status", "region"}
    value_entry = next(t for t in result.transformations if t.column == "contract_value")
    assert value_entry.operation == "numeric_conversion"
    assert value_entry.failed_rows == 0
    assert value_entry.reverted is False
    assert result.status == "ready"
    assert saved["result"] is result


def test_run_preprocess_returns_none_when_snapshot_missing() -> None:
    spec = _ground()
    profile = profile_dataset(b"a,b\n1,2\n", "csv", "dataset_contracts", "v1")
    with patch("aryx.preprocess.run.DatasetStore") as MockDatasetStore, \
         patch("aryx.preprocess.run.AnalysisDatasetStore"):
        MockDatasetStore.return_value.get_raw.return_value = None
        result = run_preprocess("dsn", 1, "dataset_contracts", spec, profile)
    assert result is None
