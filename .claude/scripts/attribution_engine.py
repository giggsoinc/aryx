#!/usr/bin/env python3
"""
Raven — Line Attribution Engine (library).

Reconciles edit records into per-line ownership spans. Pure library; no I/O.
Latest-wins within a session_id; cross-session overlaps -> joint attribution.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

_log = logging.getLogger(__name__)


def load_edits(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    rows.sort(key=lambda r: r.get("ts", ""))
    return rows


def span_from(rec: dict) -> dict:
    nr = rec.get("new_range", [0, 0]) or [0, 0]
    start, end = int(nr[0] or 0), int(nr[1] or 0)
    if start <= 0 and end <= 0:
        return {}
    if start <= 0:
        start = 1
    if end < start:
        end = start
    return {
        "start": start,
        "end": end,
        "source": rec.get("source", "ai"),
        "human": rec.get("human", ""),
        "model": rec.get("model", "") or "",
        "mode": rec.get("mode", "") or "",
        "skill": rec.get("skill", "") or "",
        "session_id": rec.get("session_id", "") or "",
        "ts": rec.get("ts", ""),
        "reason": rec.get("reason", ""),
    }


def _overlaps(a: dict, b: dict) -> bool:
    return not (a["end"] < b["start"] or b["end"] < a["start"])


def _merge_joint(a: dict, b: dict) -> dict:
    humans = sorted({h for h in (a["human"], b["human"]) if h})
    return {
        **b,
        "start": min(a["start"], b["start"]),
        "end": max(a["end"], b["end"]),
        "human": " + ".join(humans),
        "source": "joint" if a["source"] != b["source"] else b["source"],
    }


def reconcile(spans: list[dict]) -> list[dict]:
    spans = [s for s in spans if s]
    spans.sort(key=lambda s: (s["start"], s["ts"]))
    out: list[dict] = []
    for cur in spans:
        if not out:
            out.append(cur)
            continue
        prev = out[-1]
        if _overlaps(prev, cur):
            if prev["session_id"] == cur["session_id"]:
                # latest-wins inside the same session
                out[-1] = cur if cur["ts"] >= prev["ts"] else prev
            else:
                out[-1] = _merge_joint(prev, cur)
        else:
            out.append(cur)
    return out


def build_attribution_map(edits: Iterable[dict], staged_files: set[str] | None = None) -> dict[str, list[dict]]:
    by_file: dict[str, list[dict]] = {}
    for rec in edits:
        f = rec.get("file", "")
        if not f:
            continue
        if staged_files is not None and f not in staged_files:
            continue
        sp = span_from(rec)
        if not sp:
            continue
        by_file.setdefault(f, []).append(sp)
    return {f: reconcile(v) for f, v in by_file.items()}


def find_unattributed(total_lines: int, spans: list[dict]) -> list[tuple[int, int]]:
    if total_lines <= 0:
        return []
    covered = [False] * (total_lines + 1)
    for s in spans:
        for i in range(max(1, s["start"]), min(total_lines, s["end"]) + 1):
            covered[i] = True
    gaps: list[tuple[int, int]] = []
    i = 1
    while i <= total_lines:
        if covered[i]:
            i += 1
            continue
        j = i
        while j <= total_lines and not covered[j]:
            j += 1
        gaps.append((i, j - 1))
        i = j
    return gaps


