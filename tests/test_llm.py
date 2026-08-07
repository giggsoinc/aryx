"""Tests for aryx.llm's usage logging (complete_json/complete_text -> aryx_llm_call).

Built for the token-consumption observability panel: the Ask tab already logs
every call via llm_runtime.chat (source="ask"); this shared production
dispatcher (used by the planner, ontology mapping, resolution, tagging, and
everything else routed through complete_json/complete_text) previously logged
nothing at all — the observability panel would have been blind to the exact
usage this session spent hours debugging (Groq/Gemini rate limits, max_tokens).
"""
from __future__ import annotations

from types import SimpleNamespace

from aryx import llm
from aryx.broker import Broker, ModelSpec, Registry, TokenGovernor


def _broker(model: str, provider: str) -> Broker:
    registry = Registry()
    registry.add(ModelSpec(name=model, provider=provider, tier="frontier"))
    return Broker(registry, TokenGovernor({}))


def test_log_call_is_a_noop_without_a_configured_dsn(monkeypatch) -> None:
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(rdb_dsn=""))
    called = []
    monkeypatch.setattr(llm, "psycopg", SimpleNamespace(connect=lambda *a, **k: called.append(1)))
    llm._log_call("frontier", "some-model", "groq", 10, 5, 100, "pipeline")
    assert called == []  # never even tried to connect


def test_log_call_never_raises_when_the_db_write_fails(monkeypatch) -> None:
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(rdb_dsn="postgresql://x"))

    def _boom(*a, **k):
        raise RuntimeError("db is down")

    monkeypatch.setattr(llm, "psycopg", SimpleNamespace(connect=_boom))
    llm._log_call("frontier", "some-model", "groq", 10, 5, 100, "pipeline")  # must not raise


def test_log_call_writes_the_expected_row(monkeypatch) -> None:
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(rdb_dsn="postgresql://x"))
    captured: dict[str, object] = {}

    class _FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, query, params):
            captured["params"] = params

    class _FakeConn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return _FakeCursor()

    monkeypatch.setattr(llm, "psycopg", SimpleNamespace(connect=lambda *a, **k: _FakeConn()))
    llm._log_call("frontier", "gpt-oss-20b", "groq", 100, 50, 250, "pipeline")
    assert captured["params"] == ("frontier", "gpt-oss-20b", "groq", 100, 50, 250, "pipeline", None)


def test_complete_json_logs_a_pipeline_call(monkeypatch) -> None:
    logged = []
    monkeypatch.setattr(llm, "_log_call", lambda *args: logged.append(args))
    monkeypatch.setattr(llm, "openai_json", lambda spec, system, user, key: ({"kpis": []}, 40, 20))

    broker = _broker("gemini-flash-latest", "gemini")
    result = llm.complete_json(broker, "frontier", "sys", "usr", {"type": "object"})

    assert result == {"kpis": []}
    assert len(logged) == 1
    role, model, provider, pt, ct, ms, source = logged[0]
    assert (role, model, provider, pt, ct, source) == ("frontier", "gemini-flash-latest", "gemini", 40, 20, "pipeline")
    assert ms >= 0


def test_complete_text_logs_a_pipeline_call(monkeypatch) -> None:
    logged = []
    monkeypatch.setattr(llm, "_log_call", lambda *args: logged.append(args))
    monkeypatch.setattr(llm, "post_json", lambda url, body, headers:
                        {"choices": [{"message": {"content": "ok"}}],
                         "usage": {"prompt_tokens": 12, "completion_tokens": 3}})

    broker = _broker("llama-3.3-70b-versatile", "groq")
    text, in_tok, out_tok = llm.complete_text(broker, "frontier", "sys", "usr")

    assert text == "ok"
    assert (in_tok, out_tok) == (12, 3)
    assert len(logged) == 1
    role, model, provider, pt, ct, ms, source = logged[0]
    assert (role, model, provider, pt, ct, source) == (
        "frontier", "llama-3.3-70b-versatile", "groq", 12, 3, "pipeline")
