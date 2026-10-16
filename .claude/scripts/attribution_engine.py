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
        # Odoo card linkage (ODO-2): carried if an edit record already has it;
        # otherwise stamped at pre-commit. Survives _merge_joint via {**b}.
        "card_id": rec.get("card_id", "") or "",
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


def _reconcile_same_source(spans: list[dict]) -> list[dict]:
    """Original reconcile: latest-wins within a session, joint merge across."""
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


def _subtract(span: dict, cuts: list[dict]) -> list[dict]:
    """`span` minus every interval in `cuts`, as zero or more fragments."""
    pieces = [(span["start"], span["end"])]
    for c in cuts:
        nxt: list[tuple[int, int]] = []
        for s, e in pieces:
            if c["end"] < s or c["start"] > e:      # no overlap
                nxt.append((s, e))
                continue
            if s < c["start"]:                       # keep the head
                nxt.append((s, c["start"] - 1))
            if e > c["end"]:                         # keep the tail
                nxt.append((c["end"] + 1, e))
        pieces = nxt
        if not pieces:
            break
    return [{**span, "start": s, "end": e} for s, e in pieces if s <= e]


def reconcile(spans: list[dict]) -> list[dict]:
    """Reconcile spans, giving a precise AI record precedence over a vague human one.

    edit-watcher is a filesystem watcher: it sees that a file changed but not
    WHICH lines, so it stamps the whole file `source=human, 1..N` on every disk
    change — including the AI's own edits — and its later timestamp used to win
    under latest-wins. The result was that every AI span was erased and nothing
    was ever attributed to a model, which left comprehension debt with no input.

    Note this cannot be fixed by teaching the watcher to record precise ranges:
    it still cannot tell WHO changed the file, so those ranges would remain
    `human`, still overlap, and still win. Only distinguishing the sources does.

    The human span is SUBTRACTED around the AI's, not replaced by it — a human
    `1-879` overlapping an AI `1-17` must leave `18-879` with the human, or the
    AI would be credited with the whole file and the error would simply flip.

    Precedence applies ONLY to *blind* human spans — those with no `session_id`,
    which is what edit-watcher writes. A human span carrying a real session id is
    a tracked authorship claim from an actual session, and keeps the existing
    cross-session `joint` merge: two identified parties editing the same range
    genuinely share it, and collapsing that to "the AI did it" would be wrong.
    """
    spans = [s for s in spans if s]
    ai = _reconcile_same_source([s for s in spans if s.get("source") == "ai"])
    other = [s for s in spans if s.get("source") != "ai"]
    blind = _reconcile_same_source([s for s in other if not s.get("session_id")])
    tracked = [s for s in other if s.get("session_id")]

    kept: list[dict] = []
    for s in blind:
        kept.extend(_subtract(s, ai))          # AI wins over a blind whole-file stamp
    if tracked:
        # tracked human spans rejoin the AI spans under the original rules
        kept.extend(_reconcile_same_source(ai + tracked))
    else:
        kept.extend(ai)
    kept.sort(key=lambda s: (s["start"], s["ts"]))
    return kept


def norm_path(path: str) -> str:
    """Normalise a recorded path to git's form: `dir/f.py`.

    edit-watcher writes Windows-native paths (`.\\dir\\f.py`) while
    `git diff --cached --name-only` reports `dir/f.py`. These were compared as
    raw strings, so on Windows NO record ever matched a staged file: every line
    read as human-written, no attribution was ever produced, and the
    comprehension-debt score had no input at all.

    Normalising on read (rather than fixing only the writer) keeps the already
    captured history usable — including AI spans recorded before this fix.
    """
    p = (path or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _match_staged(rec_path: str, staged_norm: set[str], staged_by_len: list[str]) -> str | None:
    """Map a recorded path onto the staged path it refers to, or None.

    Records arrive in three forms: `dir/f.py` (git), `./dir/f.py` and
    `.\\dir\\f.py` (edit-watcher), and a full absolute path (the Edit/Write
    tools). Suffix matching handles all of them, and it is used in preference to
    stripping the repo root because the root is not reliably comparable: this
    repo's path contains an emoji, and the absolute records encode it
    differently from `os.getcwd()` (`S_redteam<mojibake>` vs `S_redteam❤️`), so
    a prefix test returns False for every single AI record. The repo-relative
    tail is byte-identical in both, so that is what we match on.

    Longest staged path first, so `a/b.py` wins over a staged `b.py` and a
    record is never credited to the wrong file.
    """
    if rec_path in staged_norm:
        return rec_path
    for s in staged_by_len:
        if rec_path.endswith("/" + s):
            return s
    return None


def build_attribution_map(edits: Iterable[dict], staged_files: set[str] | None = None) -> dict[str, list[dict]]:
    # Keyed by the git form — contribute_files.path is populated from this key, so
    # emitting a backslash or absolute path would create a second, duplicate file
    # row for a file already recorded by a POSIX agent and split its debt in two.
    staged_norm = {norm_path(s) for s in staged_files} if staged_files is not None else None
    staged_by_len = sorted(staged_norm, key=len, reverse=True) if staged_norm else []
    by_file: dict[str, list[dict]] = {}
    for rec in edits:
        f = norm_path(rec.get("file", ""))
        if not f:
            continue
        if staged_norm is not None:
            f = _match_staged(f, staged_norm, staged_by_len)
            if f is None:
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


