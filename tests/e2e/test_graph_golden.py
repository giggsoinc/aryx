"""The Postgres graph reader must reproduce what FalkorDB returned.

tests/fixtures/graph_golden/golden.json was captured once from live FalkorDB
(scripts/capture_graph_golden.py, before the removal). This test builds the
same deterministic fixture in a fresh workspace, runs the identical cases
against PostgresGraphReader, and compares result for result. Needs Postgres
only — FalkorDB is no longer involved.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "graph_golden"
sys.path.insert(0, str(_FIXTURE_DIR))

from build_fixture import Fixture, build_fixture  # noqa: E402
from cases import run_cases  # noqa: E402

from aryx.graph.pg_reader import PostgresGraphReader  # noqa: E402
from aryx.workspaces import WorkspaceStore  # noqa: E402

pytestmark = pytest.mark.e2e

_GOLDEN = json.loads((_FIXTURE_DIR / "golden.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built(e2e_dsn: str) -> Fixture:
    """The fixture workspace, built once and removed afterwards."""
    fx = build_fixture(e2e_dsn, f"golden_{uuid.uuid4().hex[:8]}")
    yield fx
    store = WorkspaceStore(e2e_dsn)
    try:
        store.delete(fx.workspace_id)
    finally:
        store.close()


@pytest.fixture(scope="module")
def actual(built: Fixture) -> dict[str, Any]:
    """Every golden case, run against the Postgres reader."""
    reader = PostgresGraphReader(built.dsn, built.workspace_id)
    return run_cases(reader, built)


def _diff(path: str, want: Any, got: Any, out: list[str]) -> None:
    """Collect the leaf paths where two nested results differ."""
    if isinstance(want, dict) and isinstance(got, dict):
        for key in sorted(set(want) | set(got)):
            if key not in want or key not in got:
                out.append(f"{path}/{key}: missing in "
                           f"{'golden' if key not in want else 'actual'}")
            else:
                _diff(f"{path}/{key}", want[key], got[key], out)
    elif want != got:
        out.append(f"{path}: golden={str(want)[:160]} actual={str(got)[:160]}")


def test_fixture_ranks_match_the_golden_capture(built: Fixture) -> None:
    """Same logical keys land on the same ranks, or nothing else is comparable."""
    assert built.key_rank() == _GOLDEN["meta"]["key_rank"]


@pytest.mark.parametrize("group", sorted(_GOLDEN["cases"]))
def test_group_matches_golden(group: str, actual: dict[str, Any]) -> None:
    diffs: list[str] = []
    _diff(group, _GOLDEN["cases"][group], actual[group], diffs)
    assert not diffs, f"{len(diffs)} difference(s):\n" + "\n".join(diffs[:25])
