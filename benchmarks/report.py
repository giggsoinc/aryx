"""Benchmark output: console formatting + append-only BENCHMARKS.md rows."""
from __future__ import annotations

import datetime
import subprocess
from pathlib import Path

WIKI_BENCH = Path(__file__).parent.parent / "docs" / "wiki" / "BENCHMARKS.md"

_HEADER = (
    "| date | commit | dataset | blocker | adj_mode | P | R | F1 | "
    "blocking_recall | candidates | wall_s | auto_merge | adj_from |"
)
_SEP = "|---|---|---|---|---|---|---|---|---|---|---|---|---|"


def fmt(metrics: dict) -> str:
    """One-line human-readable metrics summary."""
    return (
        f"P={metrics['precision']:.4f}  R={metrics['recall']:.4f}  "
        f"F1={metrics['f1']:.4f}  "
        f"blocking_recall={metrics['blocking_recall']:.4f}  "
        f"candidates={metrics['candidate_pairs']}  "
        f"time={metrics['wall_time']:.2f}s"
    )


def git_head() -> str:
    """Current commit SHA, or 'unknown' outside a repo."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:  # noqa: BLE001 — benchmarks must run outside git too
        return "unknown"


def append_benchmarks_row(dataset: str, blocker: str, adjmode: str,
                          commit: str, metrics: dict,
                          auto_merge: float, adj_from: float) -> None:
    """Append one self-describing row to the append-only BENCHMARKS.md."""
    date = datetime.date.today().isoformat()
    row = (
        f"| {date} | {commit[:8]} | {dataset} | {blocker} | {adjmode} | "
        f"{metrics['precision']:.4f} | {metrics['recall']:.4f} | "
        f"{metrics['f1']:.4f} | {metrics['blocking_recall']:.4f} | "
        f"{metrics['candidate_pairs']} | {metrics['wall_time']:.2f} | "
        f"{auto_merge} | {adj_from} |"
    )
    if WIKI_BENCH.exists():
        content = WIKI_BENCH.read_text()
        if _HEADER not in content:
            content += f"\n{_HEADER}\n{_SEP}\n"
        WIKI_BENCH.write_text(content + row + "\n")
    else:
        WIKI_BENCH.parent.mkdir(parents=True, exist_ok=True)
        WIKI_BENCH.write_text(
            "# Benchmarks\n\nAppend-only. Each row is self-describing.\n\n"
            f"{_HEADER}\n{_SEP}\n{row}\n"
        )


def sweep_markdown(rows: list[dict], top_n: int = 10) -> str:
    """Markdown frontier table of the top-N sweep rows by F1."""
    top = sorted(rows, key=lambda r: r["f1"], reverse=True)[:top_n]
    lines = [
        "",
        f"### Threshold Sweep — Top {top_n} by F1 (always_accept adjudication)",
        "",
        "| auto_merge | adj_from | P | R | F1 | blocking_recall |",
        "|---|---|---|---|---|---|",
    ]
    for r in top:
        lines.append(
            f"| {r['auto_merge']} | {r['adjudicate_from']} | "
            f"{r['precision']:.4f} | {r['recall']:.4f} | {r['f1']:.4f} | "
            f"{r['blocking_recall']:.4f} |"
        )
    return "\n".join(lines)
