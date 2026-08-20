"""Regression: the ARYX_ER_MAX_ADJUDICATIONS default must not silently
re-fork between code and docs.

A prior PR bumped the starter .env.example to 5 but left run.py's code
default and docs/INSTALL.md's reference snippet at 0 — three sources of
truth disagreeing. Compares the doc's value against run.py's actual
default (extracted from source, not hardcoded), so either side changing
alone fails this test instead of drifting silently again.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_py_default() -> int:
    """Extract the literal default passed to _threshold("ARYX_ER_MAX_ADJUDICATIONS", N)."""
    text = (_REPO_ROOT / "src/aryx/resolution/run.py").read_text(encoding="utf-8")
    match = re.search(
        r'_threshold\("ARYX_ER_MAX_ADJUDICATIONS",\s*(\d+)\)', text)
    assert match, "could not find the ARYX_ER_MAX_ADJUDICATIONS default in run.py"
    return int(match.group(1))


def _doc_default(path: str, pattern: str) -> int:
    text = (_REPO_ROOT / path).read_text(encoding="utf-8")
    match = re.search(pattern, text)
    assert match, f"could not find the documented default in {path}"
    return int(match.group(1))


def test_install_md_default_matches_code() -> None:
    """docs/INSTALL.md's setup snippet must match run.py's real default."""
    assert _doc_default("docs/INSTALL.md",
                        r"ARYX_ER_MAX_ADJUDICATIONS=(\d+)") == _run_py_default()


def test_env_example_default_matches_code() -> None:
    """.env.example's default must match run.py's real default."""
    assert _doc_default(".env.example",
                        r"ARYX_ER_MAX_ADJUDICATIONS=(\d+)") == _run_py_default()
