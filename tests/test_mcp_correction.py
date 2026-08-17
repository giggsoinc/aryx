"""Slice 6 — correction_propose / correction_apply MCP tools.

Mocks urllib.request.urlopen (both modules call it the same way every
other MCP dispatch module does) to verify the right path/body, without
a live API.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from aryx.mcp.correction import dispatch
from aryx.mcp.tools_correction import correction_tool_specs


def _fake_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_specs_include_both_correction_tools() -> None:
    names = {t.name for t in correction_tool_specs()}
    assert names == {"correction_propose", "correction_apply"}


def test_propose_posts_to_chat_endpoint_with_text() -> None:
    with patch("urllib.request.urlopen",
              return_value=_fake_response({"status": "proposal"})) as mock_open:
        result = dispatch("correction_propose",
                          {"workspace_id": 5, "text": "Maria is a HumanRole"})
    assert result == {"status": "proposal"}
    req = mock_open.call_args[0][0]
    assert req.full_url.endswith("/admin/workspaces/5/corrections/chat")
    body = json.loads(req.data.decode())
    assert body["text"] == "Maria is a HumanRole"
    assert body["selected_entity_id"] == 0


def test_apply_posts_to_corrections_endpoint_with_kind() -> None:
    with patch("urllib.request.urlopen",
              return_value=_fake_response({"id": 1, "kind": "retype"})) as mock_open:
        result = dispatch("correction_apply", {
            "workspace_id": 5, "kind": "retype",
            "entity_id": 42, "name": "HumanRole",
        })
    assert result["kind"] == "retype"
    req = mock_open.call_args[0][0]
    assert req.full_url.endswith("/admin/workspaces/5/corrections")
    body = json.loads(req.data.decode())
    assert body["entity_id"] == 42
    assert body["name"] == "HumanRole"


def test_dispatch_rejects_unknown_tool() -> None:
    result = dispatch("correction_zorp", {"workspace_id": 1})
    assert "error" in result
