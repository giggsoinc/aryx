"""Tests for the OpenAI-compatible JSON completion path (aryx.llm_providers).

Regression coverage for four real production issues on this path: (1) Groq's
gpt-oss reasoning models returned empty content (json_validate_failed,
failed_generation="") because the request never bounded output/reasoning
tokens, so a complex prompt could exhaust the whole completion budget on
hidden reasoning before any JSON was emitted — fixed by setting
max_tokens=4096. (2) Once the dashboard planner's target rose to 10-12
visualizations, 4096 wasn't enough headroom either — a live run got cut off
mid-JSON inside the third business_question, before any KPI/analysis/
visualization was emitted — bumped to max_tokens=8192. (3) Switching to
Gemini (also a hidden-reasoning family) hit the same truncation class again —
a live call with reasoning_effort="low" (gpt-oss's fix) still left
completion_tokens at ~1 out of a 100-token budget, so it was pinned to
reasoning_effort="minimal" instead. (3b) Google then re-pointed the
gemini-flash-latest alias and "minimal" — a Gemini 2.5-era thinking level —
became a hard HTTP 400 ("Thinking level MINIMAL is not supported for this
model"), failing every dashboard-spec draft as llm_call_failed. Moved to
"low", which measures identically on the live endpoint (17 total tokens on a
trivial JSON call, same as sending nothing; "medium" is 102, "high" 156), and
added a one-shot retry with the field dropped so the next alias roll degrades
instead of failing the job.
(4) This path never set a temperature at all, riding whichever default the
provider picks (typically 0.7-1.0, tuned for creative variety) — a plausible
contributor to the recurring missing_filter_value mistake (a model
"confidently" leaving a filter/numerator/denominator null even when the real
value was sitting right there) — pinned to 0.1 to favor reliable structured
completion over variety.
"""
from __future__ import annotations

from typing import Any

import pytest

from aryx.broker.specs import ModelSpec
from aryx import llm_providers
from aryx.llm_providers import openai_json


def _fake_response(**usage: int) -> dict[str, Any]:
    return {"choices": [{"message": {"content": '{"kpis": []}'}}],
           "usage": {"prompt_tokens": usage.get("prompt_tokens", 10),
                     "completion_tokens": usage.get("completion_tokens", 5)}}


def test_openai_json_always_bounds_max_tokens(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_post_json(url: str, body: dict[str, Any], headers: dict[str, str],
                        timeout: float | None = None) -> dict[str, Any]:
        captured.update(body)
        return _fake_response()

    monkeypatch.setattr(llm_providers, "post_json", _fake_post_json)
    spec = ModelSpec(name="grok-3", provider="xai", tier="frontier", endpoint="https://x.ai/v1")
    openai_json(spec, "sys", "usr", "key")
    assert captured["max_tokens"] == 8192
    assert captured["temperature"] == 0.1
    assert "reasoning_effort" not in captured


def test_openai_json_caps_reasoning_effort_for_gpt_oss_models(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_post_json(url: str, body: dict[str, Any], headers: dict[str, str],
                        timeout: float | None = None) -> dict[str, Any]:
        captured.update(body)
        return _fake_response()

    monkeypatch.setattr(llm_providers, "post_json", _fake_post_json)
    spec = ModelSpec(name="openai/gpt-oss-20b", provider="groq", tier="frontier",
                     endpoint="https://api.groq.com/openai/v1")
    openai_json(spec, "sys", "usr", "key")
    assert captured["max_tokens"] == 8192
    assert captured["reasoning_effort"] == "low"


def test_openai_json_caps_reasoning_effort_for_gemini_models(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_post_json(url: str, body: dict[str, Any], headers: dict[str, str],
                        timeout: float | None = None) -> dict[str, Any]:
        captured.update(body)
        return _fake_response()

    monkeypatch.setattr(llm_providers, "post_json", _fake_post_json)
    spec = ModelSpec(name="gemini-flash-latest", provider="gemini", tier="frontier",
                     endpoint="https://generativelanguage.googleapis.com/v1beta/openai")
    openai_json(spec, "sys", "usr", "key")
    assert captured["max_tokens"] == 8192
    # "minimal" was the Gemini 2.5-era thinking level and is now a hard 400
    # ("Thinking level MINIMAL is not supported for this model") on whatever
    # gemini-flash-latest resolves to. "low" is the supported equivalent —
    # measured live at the same 17 total tokens as sending nothing at all.
    assert captured["reasoning_effort"] == "low"


def test_openai_json_retries_without_reasoning_effort_on_400(monkeypatch) -> None:
    """A provider rejecting the thinking level degrades, it does not fail."""
    calls: list[dict[str, Any]] = []

    def _fake_post_json(url: str, body: dict[str, Any], headers: dict[str, str],
                        timeout: float | None = None) -> dict[str, Any]:
        calls.append(dict(body))
        if "reasoning_effort" in body:
            raise RuntimeError(
                'LLM provider error: HTTP 400 from https://x/chat/completions — '
                '{"error": {"code": 400, "message": "Thinking level MINIMAL is '
                'not supported for this model.", "status": "INVALID_ARGUMENT"}}')
        return _fake_response()

    monkeypatch.setattr(llm_providers, "post_json", _fake_post_json)
    spec = ModelSpec(name="gemini-flash-latest", provider="gemini", tier="frontier",
                     endpoint="https://generativelanguage.googleapis.com/v1beta/openai")
    openai_json(spec, "sys", "usr", "key")
    assert len(calls) == 2
    assert calls[0]["reasoning_effort"] == "low"
    assert "reasoning_effort" not in calls[1]
    # Everything else about the retried body is unchanged.
    assert calls[1]["max_tokens"] == 8192
    assert calls[1]["temperature"] == 0.1


def test_openai_json_does_not_retry_unrelated_errors(monkeypatch) -> None:
    """A 401/500/quota failure must surface, not get retried into a new shape."""
    calls: list[dict[str, Any]] = []

    def _fake_post_json(url: str, body: dict[str, Any], headers: dict[str, str],
                        timeout: float | None = None) -> dict[str, Any]:
        calls.append(dict(body))
        raise RuntimeError("LLM provider error: HTTP 401 from https://x — bad key")

    monkeypatch.setattr(llm_providers, "post_json", _fake_post_json)
    spec = ModelSpec(name="gemini-flash-latest", provider="gemini", tier="frontier",
                     endpoint="https://generativelanguage.googleapis.com/v1beta/openai")
    with pytest.raises(RuntimeError, match="HTTP 401"):
        openai_json(spec, "sys", "usr", "key")
    assert len(calls) == 1
