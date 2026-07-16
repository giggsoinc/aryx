#!/usr/bin/env python3
"""
Raven — /raven-contribute CLI dispatcher.

Subcommands:
  who <file>
  lines <file>:<a>-<b>
  audit --model X --since Y [--csv]      (Sprint A4 — Hub-backed)
  attribute <file>:<a>-<b> <email>       (Sprint A4 — Hub-backed)
  signoff <file>                         (Sprint A4 — Hub-backed)

Sprint A2 implements `who` and `lines` from the local attributions.json.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
ATTRIBUTIONS = ROOT / ".raven/state/attributions.json"


def _load() -> dict:
    if not ATTRIBUTIONS.exists():
        return {}
    try:
        return json.loads(ATTRIBUTIONS.read_text()) or {}
    except Exception:
        return {}


def _spans_for(attr: dict, file: str) -> list[dict]:
    return attr.get(file, []) or []


def _print_row(row: dict, w: csv.writer | None = None) -> None:
    if w is not None:
        w.writerow([row["start"], row["end"], row["human"], row["model"],
                    row["mode"], row["skill"], row["session_id"], row["ts"]])
    else:
        print(f"  {row['start']}-{row['end']}  human={row['human']}  "
              f"model={row['model'] or '—'}  skill={row['skill'] or '—'}  "
              f"session={row['session_id'][:8]}  ts={row['ts']}")


def cmd_who(args: list[str]) -> int:
    if not args:
        print("usage: who <file>", file=sys.stderr)
        return 2
    file = args[0]
    spans = _spans_for(_load(), file)
    if not spans:
        print(f"no attribution data for {file}")
        return 0
    latest = max((s for s in spans if s["human"]), default=None,
                  key=lambda s: s["ts"])
    owner = latest["human"] if latest else "—"
    counts: Counter = Counter()
    for s in spans:
        if s["human"]:
            counts[s["human"]] += (s["end"] - s["start"] + 1)
    print(f"file: {file}")
    print(f"owner (most recent author): {owner}")
    print("top 3 contributors (lines):")
    for h, n in counts.most_common(3):
        print(f"  {h}  {n}")
    return 0


def cmd_lines(args: list[str]) -> int:
    if not args or ":" not in args[0]:
        print("usage: lines <file>:<a>-<b>", file=sys.stderr)
        return 2
    file, rng = args[0].rsplit(":", 1)
    a_s, b_s = rng.split("-")
    a, b = int(a_s), int(b_s)
    spans = _spans_for(_load(), file)
    hits = [s for s in spans if not (s["end"] < a or s["start"] > b)]
    if not hits:
        print(f"no attribution covering {file}:{a}-{b}")
        return 0
    for s in hits:
        _print_row(s)
    return 0


def _hub_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_hub", Path(__file__).resolve().parent / "cli_hub.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def cmd_audit(args):     return _hub_module().audit(args)
def cmd_attribute(args): return _hub_module().attribute(args)
def cmd_signoff(args):   return _hub_module().signoff(args)


COMMANDS = {
    "who": cmd_who, "lines": cmd_lines, "audit": cmd_audit,
    "attribute": cmd_attribute, "signoff": cmd_signoff,
}


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: cli.py <who|lines|audit|attribute|signoff> ...", file=sys.stderr)
        return 2
    sub = argv[0]
    if sub not in COMMANDS:
        print(f"unknown subcommand: {sub}", file=sys.stderr)
        return 2
    return COMMANDS[sub](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
