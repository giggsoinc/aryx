#!/usr/bin/env python3
"""Raven — Contribute Pre-commit Check. Blocks commits with unattributed lines."""

import json, os, subprocess, sys, importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
STATE_DIR = ROOT / ".raven/state"
EDITS = STATE_DIR / "edits.jsonl"
ATTRIBUTIONS = STATE_DIR / "attributions.json"
MANIFEST = ROOT / ".raven/manifest.json"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_engine = _load("_eng", ROOT / ".claude/scripts/attribution_engine.py")


def _card_link():
    p = ROOT / ".claude/scripts/card_link.py"
    return _load("_card", p) if p.exists() else None


def _resolve_card_id() -> str:
    """The Odoo card this commit belongs to (ODO-2): commit-message trailer >
    active-card state > branch name. Best-effort, never raises."""
    cl = None
    try:
        cl = _card_link()
        if cl is None:
            return ""
        msg = ""
        for mf in (ROOT / ".git" / "COMMIT_EDITMSG", ROOT / ".git" / "MERGE_MSG"):
            try:
                if mf.exists():
                    msg = mf.read_text(encoding="utf-8", errors="replace")
                    break
            except Exception:
                pass
        # Read .git/HEAD directly — robust on an unborn branch (no initial
        # commit), where `git rev-parse --abbrev-ref HEAD` is unreliable.
        branch = ""
        try:
            head = (ROOT / ".git" / "HEAD").read_text(encoding="utf-8").strip()
            if head.startswith("ref:"):
                branch = head.split("refs/heads/", 1)[-1]
        except Exception:
            pass
        if not branch:
            try:
                branch = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT),
                    capture_output=True, text=True, timeout=10).stdout.strip()
            except Exception:
                pass
        return cl.resolve_card_id(message=msg, branch=branch)
    except Exception:
        return ""


def stamp_card_id(attr_map: dict) -> dict:
    """Stamp the resolved card_id onto every span that lacks one. A span that
    already carries a card_id (e.g. from a future per-edit capture) is left
    untouched — explicit beats inferred."""
    card = _resolve_card_id()
    if not card:
        return attr_map
    for spans in attr_map.values():
        for s in spans:
            if not s.get("card_id"):
                s["card_id"] = card
    return attr_map


def _docs_module() -> ModuleType | None:
    try:
        return _load("_docs", ROOT / ".claude/scripts/doc-writer.py")
    except Exception:
        return None


EXCLUDED = ("docs/contribute/", ".raven/", ".claude/state/")


def staged_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            stderr=subprocess.DEVNULL)
        return [ln.strip() for ln in out.decode().splitlines()
                if ln.strip() and not any(ln.strip().startswith(p) for p in EXCLUDED)]
    except Exception:
        return []


def line_count(path: Path) -> int:
    try:
        return sum(1 for _ in path.open("rb")) if path.exists() else 0
    except Exception:
        return 0


def triage_mode() -> str:
    try:
        m = json.loads(MANIFEST.read_text()) or {}
        return (m.get("contribute") or {}).get("triage_mode", "ASK").upper()
    except Exception:
        return "ASK"


def git_email() -> str:
    try:
        return subprocess.check_output(["git", "config", "user.email"],
                                       stderr=subprocess.DEVNULL, timeout=2).decode().strip()
    except Exception:
        return os.environ.get("GIT_AUTHOR_EMAIL", "unknown")


def auto_attribute(file_path: str, gap: tuple[int, int], human: str) -> None:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(), "source": "human",
        "tool": "auto-attribute", "file": file_path,
        "old_range": [gap[0], gap[0]], "new_range": [gap[0], gap[1]],
        "model": "", "mode": "", "skill": "",
        "session_id": os.environ.get("CLAUDE_SESSION_ID", ""),
        "human": human, "reason": "pre-commit auto-attribution",
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with EDITS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")


def report_gaps(gaps: dict, mode: str) -> int:
    out = ["", "  ❌ Contribute: changed lines without attribution:"]
    for f, gs in gaps.items():
        out.append(f"     {f}: " + ", ".join(f"{a}-{b}" for a, b in gs))
    out += ["", f"  Mode: {mode}. Fix: /raven-contribute attribute <f>:<a>-<b> <email>"]
    sys.stderr.write("\n".join(out) + "\n")
    return 1


def write_attributions(attr_map: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    attr_map = stamp_card_id(attr_map)   # ODO-2: link spans to the Odoo card
    ATTRIBUTIONS.write_text(json.dumps(attr_map, indent=2))
    docs = _docs_module()
    if not docs:
        return
    try:
        written = docs.write_all(attr_map)
        if written:
            subprocess.run(
                ["git", "add", "--"] + [str(p.relative_to(ROOT)) for p in written],
                cwd=str(ROOT), stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            )
    except Exception:
        pass


def main() -> int:
    files = staged_files()
    if not files:
        return 0
    edits = _engine.load_edits(EDITS)
    attr_map = _engine.build_attribution_map(edits, set(files))
    gaps: dict[str, list[tuple[int, int]]] = {}
    for f in files:
        spans = attr_map.get(f, [])
        total = line_count(ROOT / f)
        unattr = _engine.find_unattributed(total, spans)
        if unattr:
            gaps[f] = unattr
    if not gaps:
        write_attributions(attr_map)
        return 0
    mode = triage_mode()
    if mode == "AUTO":
        human = git_email()
        for f, gs in gaps.items():
            for g in gs:
                auto_attribute(f, g, human)
        edits = _engine.load_edits(EDITS)
        attr_map = _engine.build_attribution_map(edits, set(files))
        write_attributions(attr_map)
        return 0
    if mode == "ASK" and not sys.stdin.isatty():
        return report_gaps(gaps, "ASK (non-TTY → FLAG)")
    return report_gaps(gaps, mode)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"  ⚠️ Contribute check error: {exc}\n")
        sys.exit(0)
