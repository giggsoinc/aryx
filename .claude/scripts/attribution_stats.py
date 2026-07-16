#!/usr/bin/env python3
"""Raven — Attribution stats helper (library)."""

from __future__ import annotations

from collections import Counter


def stats_for(spans: list[dict], total_lines: int) -> dict:
    ai = sum(s["end"] - s["start"] + 1 for s in spans if s["source"] == "ai")
    human = sum(s["end"] - s["start"] + 1 for s in spans if s["source"] == "human")
    joint = sum(s["end"] - s["start"] + 1 for s in spans if s["source"] == "joint")
    attributed = ai + human + joint
    owner = ""
    if spans:
        latest_human = max(
            (s for s in spans if s["human"]),
            default=None,
            key=lambda s: s["ts"],
        )
        if latest_human:
            owner = latest_human["human"]
    contributors: Counter = Counter()
    for s in spans:
        if s["human"]:
            contributors[s["human"]] += (s["end"] - s["start"] + 1)
    return {
        "total_lines": total_lines,
        "ai_lines": ai,
        "human_lines": human,
        "joint_lines": joint,
        "unattributed_lines": max(0, total_lines - attributed),
        "ai_pct": round(100.0 * ai / total_lines, 1) if total_lines else 0.0,
        "owner": owner,
        "top_contributors": contributors.most_common(3),
    }
