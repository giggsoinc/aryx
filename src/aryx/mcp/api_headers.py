"""Outbound headers for MCP → Aryx REST calls.

Every MCP tool is a thin shim over the REST API, reached with plain
urllib. Those calls carried no credential at all, so the shims only worked
while `ARYX_API_AUTH` was left at its permissive default — and a
deployment that hardened the REST surface to `required` would have seen
every mutating tool start returning 401.

Set ARYX_API_KEY on the MCP process (same value as a key the API accepts,
issued via POST /admin/mcp/tokens) and it is forwarded on every request.
When unset, headers are unchanged, so local stacks running the API at its
default posture behave exactly as before.
"""
from __future__ import annotations

import os

_API_KEY_HEADER = "X-Aryx-Api-Key"


def api_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return outbound headers, including the API key when configured."""
    headers = dict(extra or {})
    key = (os.environ.get("ARYX_API_KEY") or "").strip()
    if key:
        headers[_API_KEY_HEADER] = key
    return headers


def json_headers() -> dict[str, str]:
    """Headers for a JSON request body."""
    return api_headers({"Content-Type": "application/json"})
