"""FalkorDB was removed; keep it removed.

The graph is read live from Postgres. These checks fail the build if the driver,
the old classes or the old plumbing come back, or if the service reappears in
the compose file, the dependency list or CI. They read files only: no database,
no network.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_BANNED_IN_SOURCE = re.compile(
    r"\b(import falkordb|from falkordb|FalkorStore|ws_graph|graph_url|project_graph|"
    r"project_incremental|project_auto|ProjectionStore)\b")


def _py_files() -> list[Path]:
    return [p for p in (ROOT / "src").rglob("*.py") if "__pycache__" not in p.parts]


def test_source_has_no_falkordb_driver_or_old_plumbing() -> None:
    offenders = []
    for path in _py_files():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _BANNED_IN_SOURCE.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not offenders, "FalkorDB plumbing is back:\n" + "\n".join(offenders)


def test_dependency_list_does_not_name_falkordb() -> None:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "falkordb" not in text


def test_compose_file_has_no_graph_service_or_volume() -> None:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").lower()
    for banned in ("falkordb", "graphdata", "6379"):
        assert banned not in text, f"docker-compose.yml mentions {banned!r}"


def test_ci_has_no_graph_service() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8").lower()
    for banned in ("falkordb", "6379", "graph_url"):
        assert banned not in text, f"ci.yml mentions {banned!r}"


def test_the_removed_modules_stay_removed() -> None:
    for gone in ("graph/falkor_store.py", "graph/reader.py", "project.py", "naming.py",
                 "store/projection_store.py"):
        assert not (ROOT / "src" / "aryx" / gone).exists(), f"{gone} is back"
