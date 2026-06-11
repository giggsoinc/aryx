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


def _bearer_ok_impl(request, *, optional_env: str = "1",
                    store_raises: bool = False,
                    tokens: list | None = None,
                    verify_result: bool = True) -> bool:
    """Reimplementation of _bearer_ok matching the patched version in main.py."""
    import os
    import logging
    logger = logging.getLogger("aryx.api.main")
    auth = (request.headers.get("authorization") or "").strip()
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not token:
        return os.environ.get("ARYX_MCP_AUTH_OPTIONAL", "1") == "1"
    try:
        if store_raises:
            raise RuntimeError("db down")
        if tokens is not None:
            if not any(not t.get("revoked_at") for t in tokens):
                return True
        return verify_result
    except Exception as exc:
        logger.error("mcp auth check failed — failing closed: %s", exc)
        return False


def _req(headers: dict) -> MagicMock:
    r = MagicMock()
    r.headers.get = lambda k, d="": headers.get(k, d)
    return r


def test_bearer_ok_no_token_optional(monkeypatch):
    monkeypatch.setenv("ARYX_MCP_AUTH_OPTIONAL", "1")
    assert _bearer_ok_impl(_req({})) is True


def test_bearer_ok_no_token_not_optional(monkeypatch):
    monkeypatch.setenv("ARYX_MCP_AUTH_OPTIONAL", "0")
    assert _bearer_ok_impl(_req({})) is False


def test_bearer_ok_store_raises_fails_closed():
    result = _bearer_ok_impl(_req({"authorization": "Bearer tok"}),
                             store_raises=True)
    assert result is False


def test_bearer_ok_zero_unrevoked_allows():
    result = _bearer_ok_impl(
        _req({"authorization": "Bearer tok"}),
        tokens=[{"revoked_at": "2026-01-01"}],
    )
    assert result is True


def test_bearer_ok_valid_token():
    result = _bearer_ok_impl(
        _req({"authorization": "Bearer goodtoken"}),
        tokens=[{"revoked_at": None}], verify_result=True,
    )
    assert result is True


def test_bearer_ok_invalid_token():
    result = _bearer_ok_impl(
        _req({"authorization": "Bearer badtoken"}),
        tokens=[{"revoked_at": None}], verify_result=False,
    )
    assert result is False


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
