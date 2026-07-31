"""Tests for the OpenAI-compatible JSON completion path (aryx.llm_providers).

Regression coverage for a real production failure: Groq's gpt-oss reasoning
models returned empty content (json_validate_failed, failed_generation="")
because the request never bounded output/reasoning tokens, so a complex
prompt could exhaust the whole completion budget on hidden reasoning before
any JSON was emitted.
"""
from __future__ import annotations

from typing import Any

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
    assert captured["max_tokens"] == 4096
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
    assert captured["max_tokens"] == 4096
    assert captured["reasoning_effort"] == "low"
