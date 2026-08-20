"""Slice 5 addition to Slice 3 — ingest_file MCP tool.

_encode_multipart is pure and hand-rolled (stdlib only, no requests
dependency) — worth verifying byte-for-byte, since a malformed multipart
body fails silently as a 4xx from FastAPI rather than a clear local error.
"""
from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from aryx.mcp.ingest_hitl import dispatch
from aryx.mcp.multipart import encode_multipart as _encode_multipart
from aryx.mcp.tools_ingest import ingest_tool_specs


def _fake_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_specs_now_include_five_ingest_tools() -> None:
    names = {t.name for t in ingest_tool_specs()}
    assert names == {"ingest_file", "ingest_questions", "ingest_answer",
                     "ingest_status", "entities_preview"}


def test_encode_multipart_includes_field_and_file_parts() -> None:
    body, boundary = _encode_multipart(
        {"ontology_type": "Document"},
        [("files", "a.csv", b"id,name\n1,x\n")])
    text = body.decode()
    assert f"--{boundary}" in text
    assert 'name="ontology_type"' in text
    assert "Document" in text
    assert 'name="files"; filename="a.csv"' in text
    assert "Content-Type: text/csv" in text
    assert b"id,name\n1,x\n" in body
    assert text.rstrip().endswith(f"--{boundary}--")


def test_ingest_file_decodes_base64_and_posts_multipart() -> None:
    raw = b"id,name\n1,Acme\n"
    encoded = base64.b64encode(raw).decode()
    with patch("urllib.request.urlopen",
              return_value=_fake_response({"status": "queued", "job_id": "j1"})) as mock_open:
        result = dispatch("ingest_file", {
            "workspace_id": 2,
            "files": [{"filename": "contracts.csv", "content_base64": encoded}],
        })
    assert result == {"status": "queued", "job_id": "j1"}
    req = mock_open.call_args[0][0]
    assert req.full_url.endswith("/admin/ingest/file")
    assert raw in req.data
    assert b'filename="contracts.csv"' in req.data


def test_ingest_file_forwards_file_types_map_as_json_field() -> None:
    """The per-file-typing escape hatch (see test_file_ingest_shape_guard.py)
    must actually reach the multipart body, not just the MCP tool schema."""
    raw = b"TicketID,Issue\nT1,Radio not booting\n"
    encoded = base64.b64encode(raw).decode()
    with patch("urllib.request.urlopen",
              return_value=_fake_response({"status": "queued", "job_id": "j2"})) as mock_open:
        dispatch("ingest_file", {
            "workspace_id": 2,
            "files": [{"filename": "tickets.csv", "content_base64": encoded}],
            "ontology_type": "Ticket",
            "file_types": {"tickets.csv": "Ticket"},
        })
    req = mock_open.call_args[0][0]
    assert b'name="file_types"' in req.data
    assert b'{"tickets.csv": "Ticket"}' in req.data


def test_ingest_file_omits_file_types_field_when_not_given() -> None:
    raw = b"id,name\n1,Acme\n"
    encoded = base64.b64encode(raw).decode()
    with patch("urllib.request.urlopen",
              return_value=_fake_response({"status": "queued", "job_id": "j3"})) as mock_open:
        dispatch("ingest_file", {
            "workspace_id": 2,
            "files": [{"filename": "contracts.csv", "content_base64": encoded}],
        })
    req = mock_open.call_args[0][0]
    assert b'name="file_types"\r\n\r\n\r\n' in req.data


def test_encode_multipart_rejects_crlf_in_filename() -> None:
    """raven-review finding: a crafted filename with embedded CRLF + a fake
    boundary could smuggle an extra form field (e.g. a second workspace_id)
    past the real one. Must reject, not silently encode it."""
    evil = 'a.csv"\r\n\r\n--X\r\nContent-Disposition: form-data; name="workspace_id"\r\n\r\n999\r\n--X--'
    with pytest.raises(ValueError):
        _encode_multipart({}, [("files", evil, b"data")])


def test_encode_multipart_rejects_crlf_in_field_value() -> None:
    with pytest.raises(ValueError):
        _encode_multipart({"ontology_type": "Document\r\nname=\"workspace_id\""}, [])


def test_dispatch_rejects_unknown_ingest_tool() -> None:
    result = dispatch("ingest_zorp", {"workspace_id": 1})
    assert "error" in result
