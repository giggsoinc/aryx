"""Brief -> C01 intent mapping: the whole brief must reach the dashboard.

Before UserIntent schema 1.1 this adapter dropped `scope`, `objectives`,
`questions`, and every role past the first, so a dashboard could only ever
reflect the brief's domain and aim. These tests pin the lossless path.
"""
from __future__ import annotations

from aryx.intent.from_brief import brief_to_intent_request

_BRIEF = {
    "domain": "Retail banking",
    "aim": "Spot card fraud within a day",
    "objectives": ["cut false positives", "flag new merchants"],
    "scope": "IN: card transactions  OUT: HR records",
    "roles": ["Fraud analyst", "CFO"],
    "questions": ["which merchants spike overnight?"],
}


def test_scalar_fields_map_directly() -> None:
    req = brief_to_intent_request(_BRIEF, 7)

    assert req.domain == "Retail banking"
    assert req.objective == "Spot card fraud within a day"
    assert req.target_audience == "Fraud analyst"


def test_brief_context_carries_what_has_no_scalar_home() -> None:
    req = brief_to_intent_request(_BRIEF, 7)

    assert req.brief_context is not None
    assert req.brief_context.scope == "IN: card transactions  OUT: HR records"
    assert req.brief_context.objectives == ["cut false positives",
                                            "flag new merchants"]
    assert req.brief_context.questions == ["which merchants spike overnight?"]
    # Every role survives, not just the one that fits target_audience.
    assert req.brief_context.roles == ["Fraud analyst", "CFO"]


def test_uploaded_file_falls_back_to_a_workspace_marker() -> None:
    """The brief is authored BEFORE upload — that ordering is the point."""
    req = brief_to_intent_request(_BRIEF, 7)
    assert req.uploaded_file == "brief:workspace_7"


def test_source_docs_win_over_the_workspace_marker() -> None:
    req = brief_to_intent_request({**_BRIEF, "source_docs": ["sow.pdf"]}, 7)
    assert req.uploaded_file == "sow.pdf"


def test_empty_brief_maps_without_raising() -> None:
    req = brief_to_intent_request({}, 1)

    assert req.domain == ""
    assert req.objective == ""
    assert req.target_audience == ""
    assert req.brief_context is not None
    assert req.brief_context.objectives == []


def test_newline_joined_list_fields_are_coerced() -> None:
    """MCP and older clients can post list fields as newline-joined text."""
    req = brief_to_intent_request(
        {**_BRIEF, "objectives": "one\n two \n\n", "roles": "Analyst\nCFO"}, 1)

    assert req.brief_context.objectives == ["one", "two"]
    assert req.brief_context.roles == ["Analyst", "CFO"]
    assert req.target_audience == "Analyst"
