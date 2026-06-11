"""Threshold sweep + adjudication-band analysis for the ER funnel."""
from __future__ import annotations

import itertools

from benchmarks.metrics import ADJUDICATE_FROM, AUTO_MERGE, evaluate


def frange(start: float, stop: float, step: float):
    """Inclusive float range generator."""
    val = start
    while val <= stop + 1e-9:
        yield val
        val = round(val + step, 10)


def sweep(recs, true_pairs, id_map, blocker_fn) -> list[dict]:
    """Grid over AUTO_MERGE x ADJUDICATE_FROM with always_accept adjudication.

    Returns one metrics row per (auto_merge, adjudicate_from) combination
    where the band is non-empty.
    """
    auto_merges = [round(x, 2) for x in frange(0.85, 0.97, 0.02)]
    adj_froms = [round(x, 2) for x in frange(0.80, 0.93, 0.02)]
    rows = []
    for am, af in itertools.product(auto_merges, adj_froms):
        if af >= am:
            continue
        m = evaluate(recs, true_pairs, id_map, blocker_fn,
                     auto_merge=am, adjudicate_from=af,
                     adjudicate_mode="always_accept")
        rows.append({"auto_merge": am, "adjudicate_from": af,
                     "band_width": round(am - af, 4), **m})
    return rows


def band_tp_fraction(recs, true_pairs, id_map, blocker_fn,
                     auto_merge: float = AUTO_MERGE,
                     adjudicate_from: float = ADJUDICATE_FROM) -> float:
    """Fraction of total true-positive mass inside the adjudication band.

    Computed as (TP with always_accept − TP with always_reject) / TP with
    always_accept. This number decides how wide G10 makes its review band.
    """
    accept = evaluate(recs, true_pairs, id_map, blocker_fn,
                      auto_merge=auto_merge, adjudicate_from=adjudicate_from,
                      adjudicate_mode="always_accept")
    reject = evaluate(recs, true_pairs, id_map, blocker_fn,
                      auto_merge=auto_merge, adjudicate_from=adjudicate_from,
                      adjudicate_mode="always_reject")
    total_tp = accept["tp"]
    return (accept["tp"] - reject["tp"]) / total_tp if total_tp else 0.0
