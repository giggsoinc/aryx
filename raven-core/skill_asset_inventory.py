#!/usr/bin/env python3
"""Raven skill asset identification — scan, validate, and ingest without git_scanner.

Primary entry point for /raven-asset-identification and manual developer runs.
Uses the bundled Raven skill scanner (AST + heuristics) in skill_route_scanner.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parent
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

from project_link_common import (  # noqa: E402
    apply_asset_id_credentials,
    cache_scan_report,
    load_project_link,
    project_root,
)
from project_resolve import refresh_project_link, resolve  # noqa: E402
from skill_route_scanner import run_skill_scan  # noqa: E402
from skill_scan_common import (  # noqa: E402
    build_inventory_payload,
    load_scan_report,
    validate_scan_report,
    write_scan_report,
)


def _default_report_path() -> Path:
    return project_root() / ".raven" / "state" / "skill-scan-report.json"


def _inventory_cli_path() -> Path | None:
    candidates = [
        project_root() / "agent" / "scripts" / "raven-asset-inventory.py",
        _CORE_DIR.parent / "agent" / "scripts" / "raven-asset-inventory.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _ensure_project_link() -> dict:
    link = load_project_link()
    if link.get("application_id") and link.get("organization_id"):
        return link
    result = resolve()
    if not result.get("ok"):
        raise RuntimeError(result.get("message") or "project link failed — run raven-project-link.py")
    return result.get("link") or {}


def cmd_scan(args: argparse.Namespace) -> int:
    repo = Path(args.repo or project_root()).resolve()
    report = run_skill_scan(repo, repo_name=args.repo_name or repo.name)
    errors = validate_scan_report(report)
    if errors and args.strict:
        print(json.dumps({"status": "error", "errors": errors}))
        return 1

    out = Path(args.output or _default_report_path())
    write_scan_report(report, out, phase="skill-scan")
    link = load_project_link()
    if link.get("application_id"):
        cache_scan_report(report, phase="skill-scan", link=link)

    print(json.dumps({
        "status": "ok",
        "operation": "scan",
        "report_path": str(out),
        "endpoints": len(report.get("endpoints") or []),
        "warnings": errors,
        "scanner": report.get("meta", {}).get("scanner", "raven-skill-scanner"),
    }))
    return 0 if not (errors and args.strict) else 1


def cmd_validate(args: argparse.Namespace) -> int:
    report = load_scan_report(Path(args.report_file))
    errors = validate_scan_report(report)
    status = "ok" if not errors else "error"
    print(json.dumps({"status": status, "operation": "validate", "errors": errors}))
    return 0 if not errors else 1


def cmd_ingest(args: argparse.Namespace) -> int:
    link = _ensure_project_link()
    report = load_scan_report(Path(args.report_file))
    errors = validate_scan_report(report)
    if errors:
        print(json.dumps({"status": "error", "operation": "ingest", "errors": errors}))
        return 1

    payload = build_inventory_payload(
        report,
        link,
        prune_missing=not args.no_prune,
    )
    cli = _inventory_cli_path()
    if cli is None:
        print(json.dumps({"status": "error", "detail": "raven-asset-inventory.py not found"}))
        return 1

    apply_asset_id_credentials(link)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle)
        payload_path = handle.name

    try:
        proc = subprocess.run(
            [sys.executable, str(cli), "--operation", "ingest", "--payload-file", payload_path],
            cwd=str(project_root()),
            capture_output=True,
            text=True,
            timeout=int(args.timeout),
        )
        if proc.returncode != 0:
            print(proc.stdout or proc.stderr)
            return proc.returncode
        print(proc.stdout or "{}")
        return 0
    finally:
        Path(payload_path).unlink(missing_ok=True)


def cmd_run(args: argparse.Namespace) -> int:
    if args.refresh_link:
        refresh_project_link()
    scan_args = argparse.Namespace(
        repo=args.repo,
        repo_name=args.repo_name,
        output=args.output,
        strict=True,
    )
    code = cmd_scan(scan_args)
    if code != 0:
        return code
    ingest_args = argparse.Namespace(
        report_file=str(args.output or _default_report_path()),
        no_prune=args.no_prune,
        timeout=args.timeout,
    )
    return cmd_ingest(ingest_args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Run Raven skill scanner and write report JSON")
    scan.add_argument("--repo", help="Repository root (default: project root)")
    scan.add_argument("--repo-name")
    scan.add_argument("--output", help="Report path (default: .raven/state/skill-scan-report.json)")
    scan.add_argument("--strict", action="store_true", help="Fail when validation warnings exist")
    scan.set_defaults(func=cmd_scan)

    validate = sub.add_parser("validate", help="Validate a scan report JSON file")
    validate.add_argument("--report-file", required=True)
    validate.set_defaults(func=cmd_validate)

    ingest = sub.add_parser("ingest", help="Validate report and submit ingest payload")
    ingest.add_argument("--report-file", required=True)
    ingest.add_argument("--no-prune", action="store_true")
    ingest.add_argument("--timeout", default="180")
    ingest.set_defaults(func=cmd_ingest)

    run = sub.add_parser("run", help="Scan, validate, and ingest in one step")
    run.add_argument("--repo", help="Repository root (default: project root)")
    run.add_argument("--repo-name")
    run.add_argument("--output", help="Report path (default: .raven/state/skill-scan-report.json)")
    run.add_argument("--no-prune", action="store_true")
    run.add_argument("--timeout", default="180")
    run.add_argument("--refresh-link", action="store_true")
    run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
