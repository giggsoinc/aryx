"""MCP HITL ingest dispatch — Slice 3/5.

Five tools: ingest_file starts a run; ingest_questions / ingest_answer /
ingest_status / entities_preview drive the HITL loop. Thin shim over
/admin/ingest/file + /admin/ingest-questions + /graph + /admin/jobs.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.request
import uuid
from typing import Any

_API_URL = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")
_TIMEOUT = int(os.environ.get("ARYX_MCP_POST_TIMEOUT", "60"))


def _get(path: str) -> Any:
    with urllib.request.urlopen(f"{_API_URL}{path}", timeout=30) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _post(path: str, body: dict) -> Any:
    req = urllib.request.Request(
        f"{_API_URL}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _header_safe(value: str, what: str) -> str:
    """Reject a header-bound value carrying CR/LF or a quote.

    A raw multipart body is hand-built below with plain f-strings — any
    unescaped '\\r'/'\\n' in a field value or filename would let the
    caller inject extra header lines or a fake boundary, smuggling
    additional form fields (e.g. a second workspace_id) past whatever the
    real one was. Rejecting outright is simpler and safer than trying to
    escape a value that has no real escaping rules in this format.
    """
    if any(c in value for c in ("\r", "\n", '"')):
        raise ValueError(f"{what} contains a control character or quote: {value!r}")
    return value


def _encode_multipart(fields: dict[str, str],
                      files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    """Build a multipart/form-data body by hand (stdlib only — no extra
    HTTP client dependency). Returns (body, boundary)."""
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for key, value in fields.items():
        value = _header_safe(value, f"field {key!r}")
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"'
            f"\r\n\r\n{value}\r\n".encode())
    for field_name, filename, data in files:
        filename = _header_safe(filename, "filename")
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
            + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def _post_multipart(path: str, fields: dict[str, str],
                    files: list[tuple[str, str, bytes]]) -> Any:
    body, boundary = _encode_multipart(fields, files)
    req = urllib.request.Request(
        f"{_API_URL}{path}", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310
        return json.loads(r.read().decode())


def dispatch(name: str, a: dict) -> Any:
    """Route an ingest_* MCP call to its backing REST endpoint."""
    if name == "ingest_file":
        wid = int(a["workspace_id"])
        files = [("files", f["filename"], base64.b64decode(f["content_base64"]))
                for f in a["files"]]
        fields = {
            "ontology_type": a.get("ontology_type", "Document"),
            "match_keys": a.get("match_keys", "name"),
            "fk_links": json.dumps(a.get("fk_links") or []),
            "workspace_id": str(wid),
            "graph_plan": json.dumps(a["graph_plan"]) if a.get("graph_plan") else "",
        }
        return _post_multipart("/admin/ingest/file", fields, files)
    if name == "ingest_questions":
        wid = int(a["workspace_id"])
        status = a.get("status", "pending")
        limit = int(a.get("limit", 25))
        return _get(f"/admin/ingest-questions?workspace_id={wid}"
                    f"&status={status}&limit={limit}")
    if name == "ingest_answer":
        return _post(f"/admin/ingest-questions/{int(a['question_id'])}/answer",
                     {"answer": a["answer"],
                      "answered_by": a.get("answered_by", "mcp-agent")})
    if name == "ingest_status":
        wid = int(a["workspace_id"])
        job_id = a.get("job_id", "")
        stats = _get(f"/admin/ingest-questions/stats?workspace_id={wid}"
                     f"&job_id={job_id}")
        out = {"workspace_id": wid, "question_counts": stats}
        if job_id:
            try:
                out["job"] = _get(f"/admin/jobs/{job_id}?workspace_id={wid}")
            except Exception as exc:  # noqa: BLE001
                out["job_error"] = str(exc)
        return out
    if name == "entities_preview":
        wid = int(a["workspace_id"])
        limit = int(a.get("limit", 20))
        graph = _get(f"/graph?workspace_id={wid}") or {}
        return {
            "entities": (graph.get("entities") or [])[:limit],
            "relationships": (graph.get("relationships") or [])[:limit * 3],
            "entity_total": len(graph.get("entities") or []),
            "relationship_total": len(graph.get("relationships") or []),
        }
    return {"error": f"unknown ingest tool: {name}"}
