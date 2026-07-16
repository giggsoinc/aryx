#!/usr/bin/env python3
"""
Raven — Project Doc Writer.

Renders per-file attribution markdown into docs/contribute/<file>.md.
Called from contribute-precommit.py after the attribution engine succeeds.
Result is git-add'd so the doc lands in the same commit as the source.
"""

from __future__ import annotations

import json
import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Iterable

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))).resolve()
DOCS_DIR = ROOT / "docs" / "contribute"
ATTRIBUTIONS = ROOT / ".raven/state/attributions.json"
_THIS_DIR = Path(__file__).resolve().parent


def _stats_mod() -> ModuleType:
    candidates = (_THIS_DIR / "attribution_stats.py",
                  ROOT / ".claude/scripts/attribution_stats.py")
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location("_stats", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise FileNotFoundError("attribution_stats.py not found")


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for _ in path.open("rb"))
    except Exception:
        return 0


def header(file_rel: str, stats: dict) -> str:
    lines = [
        f"# Attribution — {file_rel}",
        "",
        f"Last updated: {datetime.now(timezone.utc).isoformat()}",
        f"Total lines: {stats['total_lines']}",
        f"Lines AI-generated: {stats['ai_lines']} ({stats['ai_pct']}%)",
        f"Lines human-typed: {stats['human_lines']}",
        f"Lines joint: {stats['joint_lines']}",
        f"Lines unattributed: {stats['unattributed_lines']}",
        f"Owner (most recent author): {stats['owner'] or '—'}",
        "",
    ]
    return "\n".join(lines)


def row(span: dict) -> str:
    rng = f"{span['start']}-{span['end']}"
    # 'signer' is populated post-commit by contribute-signoff.py; until then we
    # show '—' so the column distinguishes signoff state from authorship.
    signer = span.get("signer") or "—"
    return (
        f"| {rng} | {span.get('human','—') or '—'} "
        f"| {span.get('model','') or '—'} "
        f"| {span.get('mode','') or '—'} "
        f"| {span.get('skill','') or '—'} "
        f"| {signer} "
        f"| {(span.get('commit_sha') or '—')[:8]} "
        f"| {span.get('ts','')} "
        f"| {span.get('reason','') or ''} |"
    )


def table(spans: Iterable[dict]) -> str:
    head = (
        "| Line Range | Human Author | AI Model | Mode | Skill | Signed By | Commit | Date (UTC) | Reason |\n"
        "| ---------- | ------------ | -------- | ---- | ----- | --------- | ------ | ---------- | ------ |"
    )
    body = "\n".join(row(s) for s in spans)
    return head + ("\n" + body if body else "")


def render_file_doc(file_rel: str, spans: list[dict], total: int) -> str:
    stats = _stats_mod().stats_for(spans, total)
    return header(file_rel, stats) + "\n" + table(spans) + "\n"


def write_all(attr_map: dict, out_dir: Path = DOCS_DIR) -> list[Path]:
    written: list[Path] = []
    for file_rel, spans in attr_map.items():
        target = out_dir / (file_rel + ".md")
        target.parent.mkdir(parents=True, exist_ok=True)
        total = _line_count(ROOT / file_rel)
        target.write_text(render_file_doc(file_rel, spans, total))
        written.append(target)
    return written


def main() -> int:
    if not ATTRIBUTIONS.exists():
        return 0
    try:
        attr_map = json.loads(ATTRIBUTIONS.read_text()) or {}
    except Exception:
        return 0
    write_all(attr_map)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
