"""The C09→C11→C12 contract for `Analysis.operation`.

Reproduces the workspace-37 outage: the planner paired a `histogram`
Analysis with a `count` KPI (which has no measure to bucket). C11 could not
emit a histogram template, silently fell through to `grouped_count_rows`,
and C12 — which dispatches strictly on the DECLARED operation and never
shape-sniffs — tried to read the resulting `{group: int}` as
`{group: {"buckets": ...}}`. `TypeError: 'int' object is not subscriptable`
escaped the analysis loop and killed the whole run: nine healthy analyses
discarded, dashboard never composed.

Three layers, three distinct jobs:
  C09 prevention  — reject the pairing before it compiles
  C11 honesty     — refuse to swap the result shape silently
  C12 containment — one bad analysis must never discard the others
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

for _mod in ("falkordb", "psycopg", "psycopg.types", "psycopg.types.json",
             "psycopg_pool"):
    try:
        importlib.import_module(_mod)
    except ImportError:
        sys.modules.setdefault(_mod, MagicMock())

from aryx.andie_planner.models import Analysis, DashboardSpec, Kpi
from aryx.execution_compiler.validate import check_analysis_operation_compilable
from aryx.spec_validation.checks import _histogram_metric_errors

# The exact shapes from workspace 37.
_COUNT_KPI = Kpi(kpi_id="kpi_total_entities", name="Total entities",
                 operation="count", dataset_id="ds")
_HIST_KPI = Kpi(kpi_id="kpi_latitude_hist", name="Latitude spread",
                operation="histogram", measure="latitude", dataset_id="ds")
_BAD = Analysis(analysis_id="an_latitude_distribution", operation="histogram",
                metric="kpi_total_entities", group_by=["latitude"],
                dataset_id="ds")
_GOOD = Analysis(analysis_id="an_latitude_distribution", operation="histogram",
                 metric="kpi_latitude_hist", group_by=["latitude"],
                 dataset_id="ds")


def _spec(analyses: list[Analysis], kpis: list[Kpi]) -> DashboardSpec:
    return DashboardSpec(spec_id="s", dataset_id="ds", dataset_version="v1",
                         analyses=analyses, kpis=kpis)


# --- C09: prevention -------------------------------------------------------

def test_c09_rejects_histogram_analysis_pointed_at_a_count_kpi() -> None:
    errors = _histogram_metric_errors(_spec([_BAD], [_COUNT_KPI, _HIST_KPI]))

    assert [e.code for e in errors] == ["histogram_metric_mismatch"]
    assert errors[0].path == "analysis:an_latitude_distribution.metric"
    assert errors[0].reference == "kpi_total_entities"


def test_c09_accepts_a_histogram_analysis_on_a_histogram_kpi() -> None:
    assert _histogram_metric_errors(_spec([_GOOD], [_HIST_KPI])) == []


def test_c09_rejects_a_histogram_kpi_with_no_measure_to_bucket() -> None:
    """operation='histogram' is not enough — there must be a column."""
    measureless = Kpi(kpi_id="kpi_h", name="h", operation="histogram",
                      dataset_id="ds")
    analysis = Analysis(analysis_id="an_h", operation="histogram",
                        metric="kpi_h", dataset_id="ds")

    assert len(_histogram_metric_errors(_spec([analysis], [measureless]))) == 1


def test_c09_rejects_a_histogram_analysis_whose_metric_does_not_exist() -> None:
    orphan = Analysis(analysis_id="an_h", operation="histogram",
                      metric="kpi_missing", dataset_id="ds")

    assert len(_histogram_metric_errors(_spec([orphan], [_COUNT_KPI]))) == 1


def test_c09_ignores_non_histogram_analyses() -> None:
    grouped = Analysis(analysis_id="an_g", operation="group_by",
                       metric="kpi_total_entities", group_by=["state"],
                       dataset_id="ds")

    assert _histogram_metric_errors(_spec([grouped], [_COUNT_KPI])) == []


# --- C11: honesty ----------------------------------------------------------

def test_c11_refuses_to_silently_compile_histogram_as_a_grouped_count() -> None:
    issues = check_analysis_operation_compilable(
        [_BAD], {"kpi_total_entities": _COUNT_KPI})

    assert [i.code for i in issues] == ["uncompilable_analysis_operation"]
    assert issues[0].node_id == "analysis:an_latitude_distribution"
    assert "grouped count" in issues[0].detail


def test_c11_hard_fails_the_plan_on_that_issue() -> None:
    """The issue must be a REJECTION, not an advisory note."""
    from aryx.execution_compiler.compile import _HARD_FAILURE_CODES

    assert "uncompilable_analysis_operation" in _HARD_FAILURE_CODES


def test_c11_passes_a_correctly_paired_histogram() -> None:
    assert check_analysis_operation_compilable(
        [_GOOD], {"kpi_latitude_hist": _HIST_KPI}) == []


# --- C12: containment ------------------------------------------------------

def test_c12_contains_the_exact_workspace_37_crash() -> None:
    """`grouped_count_rows` output read as a histogram must not raise."""
    from aryx.analysis_execution.run import _unpack_analysis

    # What grouped_count_rows actually returns: {group_value: count}.
    rows, error = _unpack_analysis(_BAD, {"37.7749": 12, "40.7128": 8})

    assert rows is None
    assert "an_latitude_distribution" in error
    assert "'histogram'" in error
    assert "TypeError" in error
    assert "rest of the dashboard is unaffected" in error


def test_c12_unpacks_a_well_formed_histogram_normally() -> None:
    from aryx.analysis_execution.run import _unpack_analysis

    rows, error = _unpack_analysis(_GOOD, {
        "north": {"buckets": [{"lo": 0, "hi": 10, "n": 3}], "sample_size": 3},
        "south": {"buckets": [{"lo": 0, "hi": 10, "n": 5}], "sample_size": 5},
    })

    assert error == ""
    assert rows is not None
    assert [r.group_value for r in rows] == ["north", "south"]
    assert [r.sample_size for r in rows] == [3, 5]


def test_c12_reports_the_analysis_id_so_the_user_can_act() -> None:
    """A named warning beats a silent skip — the user must learn which
    chart vanished and why."""
    from aryx.analysis_execution.run import _unpack_analysis

    _, error = _unpack_analysis(_BAD, 5)

    assert error.startswith("analysis 'an_latitude_distribution'")


def test_c12_does_not_swallow_programming_errors() -> None:
    """Containment covers SHAPE mismatches, not arbitrary bugs — a
    surprise exception type must still surface loudly."""
    from aryx.analysis_execution.run import _unpack_analysis

    class _Exploding(dict):
        def items(self):
            raise RuntimeError("store connection lost")

    try:
        _unpack_analysis(_GOOD, _Exploding())
    except RuntimeError as exc:
        assert "store connection lost" in str(exc)
    else:
        raise AssertionError("RuntimeError should not be contained")
