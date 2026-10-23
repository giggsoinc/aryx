"""Shared route-contract test client: mount one router with `get_settings`
and named store classes patched on its module.

`get_settings` is mocked in every test: the real Settings() reads this
machine's local env file, which carries Docker-only keys `Settings` (extra=
"forbid") rejects outside a container — unrelated to the routes themselves.
"""
from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class _PatchedClient:
    """Wraps TestClient so the get_settings/store patches are torn down
    right after the ONE request each test makes — `ExitStack.enter_context`
    with no matching `close()` would otherwise leak every patch past the
    test, permanently monkey-patching the real store classes for the rest
    of the pytest process (confirmed live before this wrapper existed)."""

    def __init__(self, app: FastAPI, stack: ExitStack) -> None:
        self._client = TestClient(app, raise_server_exceptions=False)
        self._stack = stack

    def __getattr__(self, name: str):
        method = getattr(self._client, name)
        def call(*args, **kwargs):
            try:
                return method(*args, **kwargs)
            finally:
                self._stack.close()
        return call


def _client(router_factory, module: str, **mocks) -> _PatchedClient:
    """Mount `router_factory`'s router with `get_settings` and every
    name in `mocks` patched on `module`, e.g. mocks=dict(DatasetStore=...)."""
    stack = ExitStack()
    stack.enter_context(patch(f"{module}.get_settings",
                              return_value=MagicMock(rdb_dsn="postgresql://test")))
    for name, target in mocks.items():
        stack.enter_context(patch(f"{module}.{name}", target))
    app = FastAPI()
    app.include_router(router_factory())
    return _PatchedClient(app, stack)
