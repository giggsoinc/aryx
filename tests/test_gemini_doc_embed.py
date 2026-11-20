"""Document chunks are embedded on Gemini when the LLM is Gemini.

Prod runs the LLM on Gemini with no Ollama service, so embedding failed with
"Name or service not known" and the whole PDF was dropped. Chunk embeddings now
use the provider's own /embeddings endpoint (768-wide, the DB column width).
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from aryx.broker import Broker, Registry, TokenGovernor
from aryx.broker import embedding as emb
from aryx.models import DocumentChunk, SourceRef
from aryx.pipeline.embed import embed_chunks

CFG = {"model": "gemini-embedding-001", "endpoint": "https://g.example/v1beta/openai",
       "api_key_ref": "K", "dimensions": 768}


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Secrets:
    def get(self, ref: str) -> str:
        return "secret-key-123"


def _fake_urlopen(monkeypatch, requests: list, fail_first: int = 0, code: int = 503):
    state = {"left": fail_first}

    def _open(req, timeout=0):
        body = json.loads(req.data)
        requests.append({"url": req.full_url, "auth": req.headers.get("Authorization"),
                         "body": body})
        if state["left"] > 0:
            state["left"] -= 1
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b"{}"))
        rows = [{"index": i, "embedding": [float(i)] * body["dimensions"]}
                for i in range(len(body["input"]))][::-1]   # out of order on purpose
        return _Resp(json.dumps({"data": rows}).encode())

    monkeypatch.setattr(emb.urllib.request, "urlopen", _open)
    monkeypatch.setattr(emb, "_sleep", lambda s: None)


def test_gemini_and_google_providers_get_a_cloud_embed_model():
    for provider in ("google", "gemini", "Gemini"):
        cfg = emb.cloud_embed_config(provider, "https://g/x/", "K", 768)
        assert cfg == {"model": "gemini-embedding-001", "endpoint": "https://g/x",
                       "api_key_ref": "K", "dimensions": 768}


def test_other_providers_and_missing_pieces_keep_the_ollama_path():
    assert emb.cloud_embed_config("ollama", "http://ollama:11434", None, 768) is None
    assert emb.cloud_embed_config("xai", "https://api.x.ai/v1", "K", 768) is None
    assert emb.cloud_embed_config("google", "https://g", None, 768) is None


def test_embed_model_can_be_overridden():
    cfg = emb.cloud_embed_config("google", "https://g", "K", 768, "my-embed")
    assert cfg["model"] == "my-embed"


def test_request_shape_order_and_batching(monkeypatch):
    requests: list = []
    _fake_urlopen(monkeypatch, requests)
    texts = [f"t{i}" for i in range(150)]
    vectors = emb.embed_openai_compatible(CFG, "secret-key-123", texts)

    assert len(vectors) == 150 and len(vectors[0]) == 768
    assert [len(r["body"]["input"]) for r in requests] == [100, 50]
    assert requests[0]["url"].endswith("/embeddings")
    assert requests[0]["auth"] == "Bearer secret-key-123"
    assert requests[0]["body"]["model"] == "gemini-embedding-001"
    assert vectors[0][0] == 0.0 and vectors[1][0] == 1.0, "restored to input order"


def test_transient_503_is_retried(monkeypatch):
    requests: list = []
    _fake_urlopen(monkeypatch, requests, fail_first=2, code=503)
    assert len(emb.embed_openai_compatible(CFG, "k", ["a", "b"])) == 2
    assert len(requests) == 3


def test_persistent_failure_raises_without_leaking_the_key(monkeypatch):
    _fake_urlopen(monkeypatch, [], fail_first=9, code=503)
    with pytest.raises(RuntimeError) as err:
        emb.embed_openai_compatible(CFG, "secret-key-123", ["a"])
    assert "503" in str(err.value) and "secret-key-123" not in str(err.value)


def test_auth_errors_are_not_retried(monkeypatch):
    requests: list = []
    _fake_urlopen(monkeypatch, requests, fail_first=9, code=401)
    with pytest.raises(RuntimeError):
        emb.embed_openai_compatible(CFG, "k", ["a"])
    assert len(requests) == 1


def _broker(doc_cfg):
    b = Broker(Registry(), TokenGovernor({}), secrets=_Secrets(),
               embed_config={"model": "nomic-embed-text", "endpoint": "http://ollama:11434"},
               doc_embed_config=doc_cfg)

    def _ollama(texts):
        raise OSError("<urlopen error [Errno -2] Name or service not known>")

    b.embed = _ollama          # Ollama is NOT available, like on prod
    return b


def _chunks(n=3):
    src = SourceRef(system="document", dataset="d", record_id="r")
    return [DocumentChunk(doc_id="d", chunk_index=i, text=f"c{i}", source=src,
                          page_slide=None, char_start=0, char_end=2) for i in range(n)]


def test_chunks_embed_on_gemini_even_though_ollama_is_down(monkeypatch):
    _fake_urlopen(monkeypatch, [])
    out = embed_chunks(_chunks(), _broker(CFG), expected_dim=768)
    assert [e.model_id for e in out] == ["gemini-embedding-001"] * 3
    assert all(e.dim == 768 for e in out)


def test_without_cloud_config_chunks_still_use_ollama():
    with pytest.raises(OSError, match="Name or service not known"):
        embed_chunks(_chunks(), _broker(None), expected_dim=768)
    assert _broker(None).doc_embed_model_id == "nomic-embed-text"


@pytest.mark.parametrize("provider,env,expect", [
    ("google", {}, "gemini-embedding-001"),
    ("gemini", {}, "gemini-embedding-001"),
    ("google", {"ARYX_EMBED_ENDPOINT": "http://ollama:11434"}, "nomic-embed-text"),
    ("ollama", {}, "nomic-embed-text"),
])
def test_ingest_broker_picks_the_embed_backend(monkeypatch, provider, env, expect):
    from aryx import llm_runtime
    from aryx.api import admin_api

    monkeypatch.delenv("ARYX_EMBED_ENDPOINT", raising=False)
    monkeypatch.delenv("ARYX_EMBED_MODEL", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(llm_runtime, "status", lambda: {
        "provider": provider, "endpoint": "https://g/v1beta/openai",
        "menial_model": "m", "answer_model": "m"})
    assert admin_api._local_broker().doc_embed_model_id == expect
