"""ER benchmark CLI — runs the REAL Aryx funnel against labeled datasets.

Usage:
  python -m benchmarks.run_bench --dataset febrl1
  python -m benchmarks.run_bench --dataset mfg --compare-legacy
  python -m benchmarks.run_bench --dataset febrl1 --sweep
  python -m benchmarks.run_bench --dataset febrl1 --quick   # CI gate mode

Modules: loaders (datasets), metrics (funnel eval), sweep (grid), report (output).
"""
from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

from benchmarks.loaders import int_to_str_map, load_dataset, to_resolution_records
from benchmarks.metrics import (ADJUDICATE_FROM, AUTO_MERGE, block_legacy,
                                block_multi, evaluate)
from benchmarks.report import append_benchmarks_row, fmt, git_head, sweep_markdown
from benchmarks.sweep import band_tp_fraction, sweep

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("benchmarks")


def _parse_args(argv) -> argparse.Namespace:
    """Build and parse the benchmark CLI arguments."""
    ap = argparse.ArgumentParser(description="Aryx ER benchmark harness")
    ap.add_argument("--dataset", default="febrl1", help="febrl1-4 | mfg")
    ap.add_argument("--compare-legacy", action="store_true",
                    help="Also run legacy prefix blocker for before/after delta")
    ap.add_argument("--sweep", action="store_true",
                    help="Grid sweep AUTO_MERGE x ADJUDICATE_FROM; emit CSV + table")
    ap.add_argument("--adjudicate", choices=["always_accept", "always_reject"],
                    default="always_reject", help="Mocked adjudication mode")
    ap.add_argument("--no-append", action="store_true",
                    help="Skip appending to BENCHMARKS.md")
    ap.add_argument("--quick", action="store_true",
                    help="Quick mode: print parseable P=x.xx R=x.xx F1=x.xx")
    return ap.parse_args(argv)


def _run_sweep(args, recs, true_pairs, id_map) -> None:
    """Run the threshold sweep, write CSV, and log the frontier table."""
    logger.info("\n=== Threshold sweep ===")
    rows = sweep(recs, true_pairs, id_map, block_multi)
    csv_path = Path("benchmarks") / f"sweep_{args.dataset}.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    logger.info("  Sweep CSV: %s", csv_path)
    logger.info(sweep_markdown(rows))
    best = sorted(rows, key=lambda r: r["f1"], reverse=True)[0]
    logger.info("\n  Recommended (NOT auto-applied — needs Conductor approval):")
    logger.info("    AUTO_MERGE      = %s", best["auto_merge"])
    logger.info("    ADJUDICATE_FROM = %s", best["adjudicate_from"])


def main(argv=None) -> dict:
    """Run the benchmark and return the multi-key metrics dict."""
    args = _parse_args(argv)

    logger.info("Loading dataset: %s", args.dataset)
    raw_records, true_pairs = load_dataset(args.dataset)
    recs = to_resolution_records(raw_records)
    id_map = int_to_str_map(recs)
    logger.info("  %d records, %d true pairs", len(recs), len(true_pairs))

    commit = git_head()

    logger.info("\n=== MultiKeyBlocker (G2) | adj=%s ===", args.adjudicate)
    m_multi = evaluate(recs, true_pairs, id_map, block_multi,
                       adjudicate_mode=args.adjudicate)
    logger.info(fmt(m_multi))

    if not args.no_append:
        append_benchmarks_row(args.dataset, "multi-key", args.adjudicate,
                              commit, m_multi, AUTO_MERGE, ADJUDICATE_FROM)

    if args.quick:
        logger.info("P=%.2f R=%.2f F1=%.2f",
                    m_multi["precision"], m_multi["recall"], m_multi["f1"])
        return m_multi

    if args.compare_legacy:
        logger.info("\n=== legacy prefix-only | adj=%s ===", args.adjudicate)
        m_leg = evaluate(recs, true_pairs, id_map, block_legacy,
                         adjudicate_mode=args.adjudicate)
        logger.info(fmt(m_leg))
        if not args.no_append:
            append_benchmarks_row(args.dataset, "legacy-prefix", args.adjudicate,
                                  commit, m_leg, AUTO_MERGE, ADJUDICATE_FROM)
        logger.info("\n  delta precision=%+.4f  delta recall=%+.4f  (headline)",
                    m_multi["precision"] - m_leg["precision"],
                    m_multi["recall"] - m_leg["recall"])

    band_frac = band_tp_fraction(recs, true_pairs, id_map, block_multi)
    logger.info("\n  Adjudication band [%s, %s) contains %.1f%% of TP mass",
                ADJUDICATE_FROM, AUTO_MERGE, band_frac * 100)
    if band_frac < 0.02:
        logger.warning("  <2%% of TP mass in band — consider widening for G10")

    if args.sweep:
        _run_sweep(args, recs, true_pairs, id_map)
    return m_multi


if __name__ == "__main__":
    main()
