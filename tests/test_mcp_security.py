"""MCP transport auth + multipart validation — PR review blockers.

Covers two confirmed findings on the MCP surface:

  #1  `_header_safe` rejected '"' on multipart FIELD values, so every
      JSON-serialised field (`fk_links`, `graph_plan`) raised ValueError
      and only an empty list ever reached the API. The values land AFTER
      the blank line — they are body bytes, never parsed as a header —
      so CR/LF is the real attack surface there. `filename` DOES sit
      inside a header line and keeps the stricter rule.

  #2  Both MCP transports were effectively open: the mounted one allowed
      any request with no token AND any request when no tokens had been
      issued; the standalone SSE server had no check at all. Since the
      tool surface mutates (ingest, corrections, charts), that was
      unauthenticated write access to the graph.
"""
from __future__ import annotations

import importlib
import json
import sys
from unittest.mock import MagicMock

for _mod in ("falkordb", "psycopg", "psycopg.types", "psycopg.types.json",
             "psycopg_pool"):
    try:
        importlib.import_module(_mod)
    except ImportError:
        sys.modules.setdefault(_mod, MagicMock())

import pytest

from aryx.mcp import auth
from aryx.mcp.api_headers import api_headers, json_headers
from aryx.mcp.multipart import _body_safe, _header_safe, encode_multipart

# --- #1: multipart field values may carry quotes -------------------------

def test_json_field_values_survive_encoding() -> None:
    """The blocker: any non-empty fk_links/graph_plan used to ValueError."""
    fields = {
        "fk_links": json.dumps([{"from": "a", "to": "b"}]),
        "graph_plan": json.dumps({"primary_types": [{"name": "Txn"}]}),
        "workspace_id": "7",
    }

    body, boundary = encode_multipart(fields, [])

    assert b'"from": "a"' in body
    assert b'"primary_types"' in body
    assert boundary.encode() in body


def test_empty_fk_links_still_works() -> None:
    """The only shape that used to get through must keep working."""
    body, _ = encode_multipart({"fk_links": json.dumps([])}, [])
    assert b"[]" in body


def test_body_values_still_reject_crlf() -> None:
    """CR/LF is the real smuggling vector — a caller must not be able to
    close the part and inject a second workspace_id."""
    smuggle = 'x\r\n--boundary\r\nContent-Disposition: form-data; name="workspace_id"\r\n\r\n999'

    with pytest.raises(ValueError, match="control character"):
        encode_multipart({"ontology_type": smuggle}, [])


def test_filename_keeps_the_stricter_quote_rule() -> None:
    """filename IS interpolated inside a header line, between quotes."""
    with pytest.raises(ValueError, match="control character or quote"):
        encode_multipart({}, [("files", 'a".csv', b"x")])

    with pytest.raises(ValueError, match="control character or quote"):
        encode_multipart({}, [("files", "a\r\n.csv", b"x")])


def test_the_two_validators_differ_only_on_quotes() -> None:
    assert _body_safe('has "quotes"', "f") == 'has "quotes"'
    assert _header_safe("no quotes", "f") == "no quotes"
    with pytest.raises(ValueError):
        _header_safe('has "quotes"', "f")


# --- #2: transport auth fails closed --------------------------------------

def test_auth_mode_defaults_to_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default posture must be closed, not open."""
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    monkeypatch.delenv("ARYX_MCP_AUTH_OPTIONAL", raising=False)

    assert auth.auth_mode() == "required"


def test_missing_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Previously returned True — the primary fail-open path."""
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    monkeypatch.delenv("ARYX_MCP_AUTH_OPTIONAL", raising=False)

    assert auth.is_authorized("") is False
    assert auth.authorize_headers(None) is False
    assert auth.authorize_headers("Basic abc") is False


def test_store_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DB hiccup must never turn into open access."""
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    monkeypatch.delenv("ARYX_MCP_AUTH_OPTIONAL", raising=False)
    monkeypatch.setattr(
        auth, "is_authorized", auth.is_authorized)  # keep real impl
    monkeypatch.setitem(sys.modules, "aryx.store.mcp_token_store", MagicMock(
        McpTokenStore=MagicMock(side_effect=RuntimeError("db down"))))

    assert auth.is_authorized("some-token") is False


def test_explicit_off_switch_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local development needs a documented, EXPLICIT opt-out."""
    monkeypatch.setenv("ARYX_MCP_AUTH", "off")
    assert auth.is_authorized("") is True

    monkeypatch.delenv("ARYX_MCP_AUTH")
    monkeypatch.setenv("ARYX_MCP_AUTH_OPTIONAL", "1")
    assert auth.auth_mode() == "off"


def test_bearer_token_is_parsed_case_insensitively() -> None:
    assert auth.token_from_header("Bearer abc123") == "abc123"
    assert auth.token_from_header("bearer  abc123 ") == "abc123"
    assert auth.token_from_header("abc123") == ""


def test_denied_hint_tells_the_operator_what_to_do() -> None:
    """A 401 with no remedy is a support ticket."""
    assert "/admin/mcp/tokens" in auth.DENIED_HINT
    assert "ARYX_MCP_AUTH=off" in auth.DENIED_HINT


# --- #2: outbound calls forward the key -----------------------------------

def test_api_key_is_forwarded_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARYX_API_KEY", "sk-test")

    assert api_headers()["X-Aryx-Api-Key"] == "sk-test"
    headers = json_headers()
    assert headers["X-Aryx-Api-Key"] == "sk-test"
    assert headers["Content-Type"] == "application/json"


def test_no_key_configured_leaves_headers_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset must behave exactly as before, so local stacks keep working."""
    monkeypatch.delenv("ARYX_API_KEY", raising=False)

    assert api_headers() == {}
    assert json_headers() == {"Content-Type": "application/json"}


def test_extra_headers_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARYX_API_KEY", "sk-test")
    headers = api_headers({"Content-Type": "multipart/form-data; boundary=x"})

    assert headers["Content-Type"].startswith("multipart/form-data")
    assert headers["X-Aryx-Api-Key"] == "sk-test"


def test_every_mcp_shim_sends_headers_on_outbound_calls() -> None:
    """Regression guard: a new shim must not reintroduce a bare urlopen.

    Each module below reaches the REST API; all of them must route through
    api_headers/json_headers so a hardened deployment does not 401.
    """
    import pathlib
    mcp_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "aryx" / "mcp"
    for name in ("onboard", "ingest_hitl", "chart", "correction",
                 "datasource", "read", "ontology"):
        source = (mcp_dir / f"{name}.py").read_text()
        assert "api_headers" in source, f"{name}.py sends no API key"
        assert 'urlopen(f"' not in source, f"{name}.py has a bare urlopen"


# --- #2: the SSE transport actually enforces it ---------------------------

def _sse_client(monkeypatch: pytest.MonkeyPatch, *, verify: bool):
    """A TestClient over the real sse.app, with the token store stubbed."""
    from starlette.testclient import TestClient
    store = MagicMock()
    store.verify.return_value = verify
    monkeypatch.setitem(sys.modules, "aryx.store.mcp_token_store",
                        MagicMock(McpTokenStore=MagicMock(return_value=store)))
    from aryx.mcp import sse
    return TestClient(sse.app)


def test_sse_app_rejects_unauthenticated_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The P1: this transport previously had NO auth of any kind.

    Guards the `middleware=[Middleware(BearerAuthMiddleware)]` wiring —
    removing it makes this test fail rather than silently reopening the
    tool surface.
    """
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    monkeypatch.delenv("ARYX_MCP_AUTH_OPTIONAL", raising=False)
    client = _sse_client(monkeypatch, verify=False)

    assert client.get("/sse").status_code == 401


def test_sse_messages_channel_is_also_protected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool calls travel on /messages/, not /sse.

    Authenticating only the stream would be theatre — a caller holding a
    session id could POST tool calls straight to the Mount.
    """
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    monkeypatch.delenv("ARYX_MCP_AUTH_OPTIONAL", raising=False)
    client = _sse_client(monkeypatch, verify=False)

    resp = client.post("/messages/?session_id=abc", json={})
    assert resp.status_code == 401


def test_sse_rejection_explains_how_to_authenticate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    monkeypatch.delenv("ARYX_MCP_AUTH_OPTIONAL", raising=False)
    client = _sse_client(monkeypatch, verify=False)

    body = client.get("/sse").json()
    assert "/admin/mcp/tokens" in body["error"]


def test_sse_rejects_a_token_the_store_does_not_recognise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    monkeypatch.delenv("ARYX_MCP_AUTH_OPTIONAL", raising=False)
    client = _sse_client(monkeypatch, verify=False)

    resp = client.get("/sse", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_sse_app_actually_wires_the_auth_middleware() -> None:
    """Structural guard — fails FAST if the middleware is unwired.

    The behavioural tests above return 401 immediately while the middleware
    is present, but if it is removed `GET /sse` opens the event stream and
    blocks instead of failing, so those tests would HANG rather than report.
    A hung test is a CI timeout, not a diagnosis. Assert the wiring itself
    so removing it fails in milliseconds with an obvious message.
    """
    from aryx.mcp import sse
    installed = [m.cls.__name__ for m in sse.app.user_middleware]

    assert "BearerAuthMiddleware" in installed, (
        "BearerAuthMiddleware is not wired into sse.app — the MCP tool "
        "surface is unauthenticated")
