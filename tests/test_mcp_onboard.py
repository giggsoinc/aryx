"""Slice 1 — Workspace + Brief MCP smoke test.

Validates the dispatch shape and quiz state machine without a live API:
``_next_question`` returns prompts in order, ``_depth`` maps populated
field count to the right readiness label.
"""
from __future__ import annotations

from aryx.mcp.onboard import _BRIEF_FIELDS, _depth, _next_question


def test_next_question_walks_fields_in_order() -> None:
    """domain → aim → objectives → scope → roles → questions, then None."""
    brief: dict = {}
    assert _next_question(brief).startswith("domain:")
    brief["domain"] = "x"
    assert _next_question(brief).startswith("aim:")
    brief["aim"] = "y"
    assert _next_question(brief).startswith("objectives:")
    brief["objectives"] = ["one"]
    assert _next_question(brief).startswith("scope:")
    brief["scope"] = "z"
    assert _next_question(brief).startswith("roles:")
    brief["roles"] = ["pm"]
    assert _next_question(brief).startswith("questions:")
    brief["questions"] = ["which merchants spike?"]
    assert _next_question(brief) is None


def test_quiz_never_reports_complete_without_proof_questions() -> None:
    """Regression: the quiz used to walk only five fields, so an
    MCP-onboarded brief was declared complete with `questions` empty.

    Proof questions are not cosmetic — aryx.brief.serialize emits them into
    every extraction prompt, and intent.brief_context carries them to the
    dashboard planner. A brief without them steers neither.
    """
    assert "questions" in _BRIEF_FIELDS
    five_of_six = {"domain": "x", "aim": "y", "objectives": ["o"],
                   "scope": "s", "roles": ["r"]}

    assert _next_question(five_of_six) is not None
    assert _depth(five_of_six) != _depth({**five_of_six, "questions": ["q"]})


def test_depth_label_matches_populated_field_count() -> None:
    """0 fields = Generic NER, 3 = Sharp, all six = Expert."""
    assert _depth({}) == "Generic NER"
    assert _depth({"domain": "x"}) == "Grounded"
    assert _depth({"domain": "x", "aim": "y", "objectives": ["o"]}) == "Sharp"
    full = {"domain": "x", "aim": "y", "objectives": ["o"],
            "scope": "s", "roles": ["r"], "questions": ["q"]}
    assert _depth(full) == "Expert"
    # Never index past the label table, whatever the field count.
    assert _depth({**full, "extra": "ignored"}) == "Expert"


def test_specs_include_all_seven_onboard_tools() -> None:
    """The 7 onboarding tool names register cleanly via tool_specs()."""
    from aryx.mcp.tools_onboard import onboard_tool_specs
    names = {t.name for t in onboard_tool_specs()}
    assert names == {
        "workspace_list", "workspace_create", "workspace_select",
        "brief_get", "brief_draft", "brief_set", "brief_save",
    }


def test_brief_set_accepts_questions_as_a_field() -> None:
    """The tool schema must let an agent SET what the quiz now asks for."""
    from aryx.mcp.tools_onboard import onboard_tool_specs
    spec = next(t for t in onboard_tool_specs() if t.name == "brief_set")
    allowed = spec.inputSchema["properties"]["field"]["enum"]

    assert set(allowed) == set(_BRIEF_FIELDS)


def test_dispatch_rejects_unknown_tool() -> None:
    """Unknown tool returns a structured error, doesn't raise."""
    from aryx.mcp.onboard import dispatch
    result = dispatch("brief_zorp", {"workspace_id": 1})
    assert "error" in result
