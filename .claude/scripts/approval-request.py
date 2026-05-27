#!/usr/bin/env python3
"""
Raven Enterprise — Approval Request
Async hook. Fires when a developer requests use of a blocked or unregistered resource.

Triggered by: mcp-guard.py (hard mode, unregistered MCP) or tool-guard.py (restricted action).
Posts to Hub approval queue. Sends email to admin. No block — developer waits for async approval.

Usage:
  python3 approval-request.py --type mcp_registration --resource slack --project acme-api
  python3 approval-request.py --type tool_use --resource "rm -rf /data" --project acme-api
  echo '{"type": "mcp_registration", "resource": "slack", "project": "acme-api"}' | python3 approval-request.py
"""

import json, os, sys, argparse, urllib.request, urllib.error, smtplib
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime, timezone

MANIFEST_PATH = Path(".raven/manifest.json")
SECRETS_PATH  = Path(".raven/manifest.secrets.json")
QUEUE_PATH    = Path(".raven/.cache/approval-queue.json")

def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text()) if path.exists() else (default or {})
    except Exception:
        return default or {}

def post_to_hub(hub_url: str, payload: dict) -> str | None:
    """POST approval request to Hub. Returns approval_id or None."""
    url = hub_url.rstrip("/") + "/api/v1/approvals"
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "X-Raven-Agent": "enterprise-v1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status in (200, 201):
                body = json.loads(resp.read())
                return body.get("id")
    except Exception:
        pass
    return None

def queue_locally(request: dict):
    """Fall back to local queue if Hub unreachable."""
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    queue = load_json(QUEUE_PATH, default=[])
    queue.append(request)
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))

def send_email_notification(secrets: dict, request: dict):
    """Email admin with approval link."""
    smtp_host  = secrets.get("smtp_host", os.environ.get("SMTP_HOST", ""))
    smtp_port  = int(secrets.get("smtp_port", os.environ.get("SMTP_PORT", 587)))
    smtp_user  = secrets.get("smtp_user", os.environ.get("SMTP_USER", ""))
    smtp_pass  = secrets.get("smtp_password", os.environ.get("SMTP_PASSWORD", ""))
    from_email = secrets.get("smtp_from", os.environ.get("SMTP_FROM", "raven@giggso.com"))
    admin_email = secrets.get("admin_email", os.environ.get("HUB_ALERT_EMAIL", ""))

    if not admin_email or not smtp_host:
        return

    hub_url     = request.get("hub_url", "")
    approval_id = request.get("approval_id", "pending")
    resource    = request.get("resource", "unknown")
    req_type    = request.get("type", "unknown")
    requested_by = request.get("requested_by", "unknown")
    project     = request.get("project", "unknown")

    approve_url = f"{hub_url}/api/v1/approvals/{approval_id}/approve" if hub_url else "N/A"
    deny_url    = f"{hub_url}/api/v1/approvals/{approval_id}/deny" if hub_url else "N/A"

    subject = f"[Raven] Approval needed: {req_type} — {resource} ({project})"
    body = f"""
Raven Enterprise — Approval Required
=====================================

Developer: {requested_by}
Project:   {project}
Type:      {req_type}
Resource:  {resource}
Requested: {request.get('ts', 'now')}

Approve:   {approve_url}
Deny:      {deny_url}

This request was submitted automatically by Raven Enterprise governance.
The developer is waiting. Unresolved requests auto-expire in 24 hours.
"""
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"]    = from_email
        msg["To"]      = admin_email
        msg.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            if smtp_user:
                s.login(smtp_user, smtp_pass)
            s.send_message(msg)
    except Exception:
        pass

def main():
    # Accept both CLI args and stdin JSON
    if not sys.stdin.isatty():
        try:
            raw  = sys.stdin.read().strip()
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
    else:
        data = {}

    parser = argparse.ArgumentParser()
    parser.add_argument("--type",     default=data.get("type", ""))
    parser.add_argument("--resource", default=data.get("resource", ""))
    parser.add_argument("--project",  default=data.get("project", ""))
    parser.add_argument("--reason",   default=data.get("reason", ""))
    args = parser.parse_args()

    if not args.type or not args.resource:
        sys.exit(0)   # Nothing actionable

    manifest     = load_json(MANIFEST_PATH)
    secrets      = load_json(SECRETS_PATH)
    hub_url      = manifest.get("hub_url") or secrets.get("hub_url", "")
    org          = manifest.get("org", "")
    project      = args.project or manifest.get("project", os.path.basename(os.getcwd()))
    requested_by = (
        manifest.get("user_email")
        or os.environ.get("GIT_AUTHOR_EMAIL")
        or os.environ.get("USER", "unknown")
    )

    request = {
        "type":         args.type,
        "resource":     args.resource,
        "project":      project,
        "org":          org,
        "requested_by": requested_by,
        "reason":       args.reason,
        "ts":           datetime.now(timezone.utc).isoformat(),
        "hub_url":      hub_url,
    }

    # Attempt Hub post
    approval_id = None
    if hub_url:
        approval_id = post_to_hub(hub_url, request)

    if approval_id:
        request["approval_id"] = approval_id
        print(f"\n📬 Approval request submitted (ID: {approval_id})", flush=True)
        print(f"   Type:     {args.type}", flush=True)
        print(f"   Resource: {args.resource}", flush=True)
        print(f"   Admin has been notified. You'll receive approval via email.", flush=True)
    else:
        # Hub unreachable — queue locally and notify anyway
        request["approval_id"] = f"local-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        queue_locally(request)
        print(f"\n📬 Approval request queued locally (Hub unreachable).", flush=True)
        print(f"   Will sync to Hub on next session when Hub is reachable.", flush=True)

    # Always attempt email notification
    send_email_notification(secrets, request)

    # Output additionalContext so Claude knows to tell the developer
    output = {
        "hookSpecificOutput": {
            "hookEventName":    "PreToolUse",
            "additionalContext": (
                f"APPROVAL REQUESTED: {args.type} for '{args.resource}' in {project}. "
                f"Admin notified. Approval ID: {request['approval_id']}. "
                f"Do NOT proceed with this action until approval is confirmed."
            ),
        }
    }
    print(json.dumps(output))

if __name__ == "__main__":
    main()
