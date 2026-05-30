"""Unified chat client. Local Ollama + OpenAI-compatible cloud, stdlib only.

Returns content plus token usage and latency so every call can be metered.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from aryx.llm.config import LlmConfig


@dataclass
class ChatResult:
    """Outcome of one chat call, including usage for observability."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    error: str = ""


def _post(url: str, body: dict, headers: dict, timeout: int) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read())


def _ollama(messages: list[dict], model: str, think: bool, cfg: LlmConfig) -> dict:
    return _post(
        f"{cfg.base_url}/api/chat",
        {"model": model, "messages": messages, "stream": False,
         "think": think, "options": {"temperature": 0.2}},
        {"Content-Type": "application/json"},
        cfg.timeout,
    )


def _cloud(messages: list[dict], model: str, cfg: LlmConfig) -> dict:
    base = "https://api.openai.com/v1" if cfg.provider == "openai" else cfg.base_url
    return _post(
        f"{base}/chat/completions",
        {"model": model, "messages": messages, "temperature": 0.2},
        {"Content-Type": "application/json", "Authorization": f"Bearer {cfg.cloud_api_key}"},
        cfg.timeout,
    )


def chat(messages: list[dict], model: str, cfg: LlmConfig, think: bool = False) -> ChatResult:
    """Send a chat completion; never raises — failures land in ChatResult.error."""
    start = time.monotonic()
    try:
        if cfg.cloud_api_key and cfg.provider != "ollama":
            raw = _cloud(messages, model, cfg)
            choice = raw["choices"][0]["message"]["content"]
            usage = raw.get("usage", {})
            pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        else:
            raw = _ollama(messages, model, think, cfg)
            choice = raw.get("message", {}).get("content", "")
            pt, ct = raw.get("prompt_eval_count", 0), raw.get("eval_count", 0)
        elapsed = int((time.monotonic() - start) * 1000)
        return ChatResult(choice.strip(), model, pt, ct, elapsed)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, TimeoutError) as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return ChatResult("", model, 0, 0, elapsed, error=str(exc))
