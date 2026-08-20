"""Tests for G4: fail-closed bearer auth + API-key middleware."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Stub heavy infrastructure so modules can be imported without Docker deps
for _mod in ("falkordb", "psycopg", "psycopg.types.json"):
    sys.modules.setdefault(_mod, MagicMock())


def _req(headers: dict) -> MagicMock:
    """A request stub exposing only `.headers.get`, as authorize_headers uses."""
    r = MagicMock()
    r.headers.get = lambda k, d="": headers.get(k, d)
    return r


# --- bearer auth, exercised against the REAL implementation ----------------
#
# These previously ran against a `_bearer_ok_impl` copy pasted into this
# file. A mirror passes whatever the production code does — it stayed green
# through a change that inverted the auth posture, and would stay green if
# the real function were deleted. Import the real thing instead:
# aryx.mcp.auth.authorize_headers is what BOTH MCP transports call now
# (mcp_mount.py's BearerAuthMiddleware and sse.py's), so testing it here
# covers both call sites at once.

def _no_auth_env(monkeypatch) -> None:
    """Clear both opt-out switches so the default posture is under test."""
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    monkeypatch.delenv("ARYX_MCP_AUTH_OPTIONAL", raising=False)


def test_bearer_ok_no_token_is_rejected(monkeypatch):
    """Default is fail-CLOSED. This asserted True while the old default was
    'optional' — the single change that made the transport open by default."""
    from aryx.mcp.auth import authorize_headers
    _no_auth_env(monkeypatch)

    assert authorize_headers(_req({}).headers.get("authorization")) is False


def test_bearer_ok_explicit_off_allows(monkeypatch):
    """Local development keeps a documented, explicit escape hatch."""
    from aryx.mcp.auth import authorize_headers
    monkeypatch.setenv("ARYX_MCP_AUTH", "off")

    assert authorize_headers(_req({}).headers.get("authorization")) is True


def test_bearer_ok_legacy_optional_flag_still_honoured(monkeypatch):
    """Anyone who deliberately set the old flag keeps their behaviour."""
    from aryx.mcp.auth import authorize_headers
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    monkeypatch.setenv("ARYX_MCP_AUTH_OPTIONAL", "1")

    assert authorize_headers(_req({}).headers.get("authorization")) is True


def test_bearer_ok_store_raises_fails_closed(monkeypatch):
    """A DB outage must never become open access."""
    from aryx.mcp import auth
    _no_auth_env(monkeypatch)
    monkeypatch.setitem(sys.modules, "aryx.store.mcp_token_store",
                        MagicMock(McpTokenStore=MagicMock(
                            side_effect=RuntimeError("db down"))))

    assert auth.is_authorized("tok") is False


def test_bearer_ok_zero_unrevoked_now_rejects(monkeypatch):
    """Was `test_bearer_ok_zero_unrevoked_allows` and asserted True.

    'No tokens issued' used to mean 'allow everyone', so a fresh deployment
    served every caller. A store with no live token now verifies to False
    like any other unrecognised token.
    """
    from aryx.mcp import auth
    _no_auth_env(monkeypatch)
    store = MagicMock()
    store.verify.return_value = False
    monkeypatch.setitem(sys.modules, "aryx.store.mcp_token_store",
                        MagicMock(McpTokenStore=MagicMock(return_value=store)))

    assert auth.is_authorized("tok") is False


def test_bearer_ok_valid_token(monkeypatch):
    from aryx.mcp.auth import authorize_headers
    _no_auth_env(monkeypatch)
    store = MagicMock()
    store.verify.return_value = True
    monkeypatch.setitem(sys.modules, "aryx.store.mcp_token_store",
                        MagicMock(McpTokenStore=MagicMock(return_value=store)))

    assert authorize_headers("Bearer goodtoken") is True


def test_bearer_ok_invalid_token(monkeypatch):
    from aryx.mcp.auth import authorize_headers
    _no_auth_env(monkeypatch)
    store = MagicMock()
    store.verify.return_value = False
    monkeypatch.setitem(sys.modules, "aryx.store.mcp_token_store",
                        MagicMock(McpTokenStore=MagicMock(return_value=store)))

    assert authorize_headers("Bearer badtoken") is False


def _mini_app(mode: str):
    os.environ["ARYX_API_AUTH"] = mode
    from fastapi import FastAPI

    from aryx.api.security import ApiKeyMiddleware
    app = FastAPI()
    app.add_middleware(ApiKeyMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def test_middleware_required_no_key(monkeypatch):
    monkeypatch.setenv("ARYX_API_AUTH", "required")
    with patch("aryx.api.security._verify_key", return_value=False):
        client = TestClient(_mini_app("required"), raise_server_exceptions=False)
        resp = client.get("/ping")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing or invalid api key"


def test_middleware_required_valid_key(monkeypatch):
    monkeypatch.setenv("ARYX_API_AUTH", "required")
    with patch("aryx.api.security._verify_key", return_value=True):
        client = TestClient(_mini_app("required"), raise_server_exceptions=False)
        resp = client.get("/ping", headers={"X-Aryx-Api-Key": "valid"})
    assert resp.status_code == 200


def test_middleware_exempt_path_open(monkeypatch):
    monkeypatch.setenv("ARYX_API_AUTH", "required")
    with patch("aryx.api.security._verify_key", return_value=False):
        client = TestClient(_mini_app("required"), raise_server_exceptions=False)
        resp = client.get("/health")
    assert resp.status_code == 200


def test_middleware_optional_warning_header(monkeypatch):
    monkeypatch.setenv("ARYX_API_AUTH", "optional")
    with patch("aryx.api.security._verify_key", return_value=False):
        client = TestClient(_mini_app("optional"), raise_server_exceptions=False)
        resp = client.get("/ping")
    assert resp.status_code == 200
    assert "X-Aryx-Auth-Warning" in resp.headers


def test_verify_key_fails_closed_on_store_exception():
    from aryx.api.security import _verify_key
    # get_settings is imported inside the function; patch its source location
    with patch("aryx.config.get_settings", side_effect=RuntimeError("no db")):
        result = _verify_key("anykey")
    assert result is False


# --- mount_mcp: the Mount, not just the SSE handshake, must be gated ------
#
# The regression this section exists to catch: mount_mcp() used to append
# two routes directly to the parent app's router — a Route("/mcp",
# handle_sse) that checked auth inline, and a sibling
# Mount("/mcp/messages/", app=sse.handle_post_message) that checked
# nothing. GET /mcp correctly 401'd; POST /mcp/messages/?session_id=<any>
# reached the raw MCP transport with zero auth — confirmed live during
# review (400 "unknown session", never 401). Fixed by building mount_mcp's
# routes as a Starlette sub-app carrying its own `middleware=[...]`, then
# mounting that whole sub-app, so BearerAuthMiddleware runs for every
# route inside it — including the Mount.

def _mcp_client(monkeypatch: pytest.MonkeyPatch, *, verify: bool):
    """A TestClient over a real FastAPI app with mount_mcp() applied."""
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    monkeypatch.delenv("ARYX_MCP_AUTH_OPTIONAL", raising=False)
    store = MagicMock()
    store.verify.return_value = verify
    monkeypatch.setitem(sys.modules, "aryx.store.mcp_token_store",
                        MagicMock(McpTokenStore=MagicMock(return_value=store)))

    from fastapi import FastAPI

    from aryx.api.mcp_mount import mount_mcp
    app = FastAPI()
    mount_mcp(app)
    return TestClient(app)


def test_mount_mcp_sse_handshake_rejects_no_token(monkeypatch):
    client = _mcp_client(monkeypatch, verify=False)

    assert client.get("/mcp", timeout=5).status_code == 401


def test_mount_mcp_messages_channel_rejects_no_token(monkeypatch):
    """This is the exact request that used to reach the transport unchecked."""
    client = _mcp_client(monkeypatch, verify=False)

    resp = client.post("/mcp/messages/?session_id=guessed", json={}, timeout=5)

    assert resp.status_code == 401


def test_mount_mcp_messages_channel_rejects_a_bad_token(monkeypatch):
    client = _mcp_client(monkeypatch, verify=False)

    resp = client.post("/mcp/messages/?session_id=guessed", json={},
                       headers={"Authorization": "Bearer nope"}, timeout=5)

    assert resp.status_code == 401


def test_mount_mcp_wires_the_shared_bearer_middleware(monkeypatch):
    """Structural guard — fails fast if the middleware is ever unwired,
    rather than the behavioural tests above hanging on a live SSE stream."""
    monkeypatch.delenv("ARYX_MCP_AUTH", raising=False)
    from fastapi import FastAPI

    from aryx.api.mcp_mount import mount_mcp
    from aryx.mcp.auth import BearerAuthMiddleware
    app = FastAPI()
    mount_mcp(app)

    mcp_route = next(r for r in app.router.routes if getattr(r, "path", "") == "/mcp")
    mounted_names = [m.cls.__name__ for m in mcp_route.app.user_middleware]

    assert BearerAuthMiddleware.__name__ in mounted_names
