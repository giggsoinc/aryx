"""Slice 7 — chart_draft / chart_confirm (ask-to-visualize) MCP tools."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from aryx.mcp.chart import dispatch
from aryx.mcp.tools_chart import chart_tool_specs


def _fake_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_specs_include_both_chart_tools() -> None:
    names = {t.name for t in chart_tool_specs()}
    assert names == {"chart_draft", "chart_confirm"}


def test_draft_posts_workspace_id_as_query_param_not_body() -> None:
    with patch("urllib.request.urlopen",
              return_value=_fake_response({"status": "valid"})) as mock_open:
        result = dispatch("chart_draft", {
            "workspace_id": 3, "dataset_id": "ds1",
            "request_text": "show revenue by region",
        })
    assert result == {"status": "valid"}
    req = mock_open.call_args[0][0]
    assert req.full_url.endswith("/andie-planner/delta/draft?workspace_id=3")
    body = json.loads(req.data.decode())
    assert body["dataset_id"] == "ds1"
    assert body["tier"] == "frontier"  # default applied


def test_confirm_passes_through_spec_items_unmodified() -> None:
    kpi = {"kpi_id": "k1", "operation": "sum"}
    with patch("urllib.request.urlopen",
              return_value=_fake_response({"status": "valid"})) as mock_open:
        dispatch("chart_confirm", {
            "workspace_id": 3, "dataset_id": "ds1", "new_kpi": kpi,
        })
    req = mock_open.call_args[0][0]
    assert req.full_url.endswith("/andie-planner/delta/confirm?workspace_id=3")
    body = json.loads(req.data.decode())
    assert body["new_kpi"] == kpi
    assert body["new_analysis"] is None


def test_dispatch_rejects_unknown_tool() -> None:
    result = dispatch("chart_zorp", {"workspace_id": 1})
    assert "error" in result
