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
    # restored to input order: vector 0 is the zero vector (left as is), vector 1 is
    # [1, 1, ...] and comes back unit length
    assert vectors[0][0] == 0.0
    assert abs(vectors[1][0] - 1 / 768 ** 0.5) < 1e-9
    assert abs(sum(x * x for x in vectors[1]) - 1.0) < 1e-9


def test_embeddings_are_unit_length_so_inner_product_and_cosine_agree():
    """Review #56: shortened gemini-embedding-001 vectors are not unit length."""
    assert abs(sum(x * x for x in emb._unit([3.0, 4.0])) - 1.0) < 1e-12
    assert emb._unit([3.0, 4.0]) == [0.6, 0.8]
    assert emb._unit([0.0, 0.0]) == [0.0, 0.0]            # no division by zero


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
    monkeypatch.delenv("ARYX_EMBED_PROVIDER", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(admin_api, "_ollama_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(llm_runtime, "status", lambda: {
        "provider": provider, "endpoint": "https://g/v1beta/openai",
        "menial_model": "m", "answer_model": "m"})
    assert admin_api._local_broker().doc_embed_model_id == expect


# ---- the switch to the provider's embeddings is never silent (review #56) -------

def _embed_model(monkeypatch, *, ollama_up, env=None, provider="google"):
    from aryx import llm_runtime
    from aryx.api import admin_api

    for name in ("ARYX_EMBED_ENDPOINT", "ARYX_EMBED_MODEL", "ARYX_EMBED_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(admin_api, "_ollama_reachable", lambda *_a, **_k: ollama_up)
    monkeypatch.setattr(llm_runtime, "status", lambda: {
        "provider": provider, "endpoint": "https://g/v1beta/openai",
        "menial_model": "m", "answer_model": "m"})
    return admin_api._local_broker().doc_embed_model_id


def test_a_deployment_with_a_working_ollama_keeps_its_own_embeddings(monkeypatch):
    """The default compose file ships an Ollama sidecar; upgrading must not move its
    chunk text to Gemini or start mixing two embedding models in one column."""
    assert _embed_model(monkeypatch, ollama_up=True) == "nomic-embed-text"


def test_without_any_ollama_the_provider_embeds(monkeypatch):
    assert _embed_model(monkeypatch, ollama_up=False) == "gemini-embedding-001"


def test_the_provider_can_be_forced_or_refused_explicitly(monkeypatch):
    assert _embed_model(monkeypatch, ollama_up=True,
                        env={"ARYX_EMBED_PROVIDER": "cloud"}) == "gemini-embedding-001"
    assert _embed_model(monkeypatch, ollama_up=False,
                        env={"ARYX_EMBED_PROVIDER": "ollama"}) == "nomic-embed-text"
    assert _embed_model(monkeypatch, ollama_up=False,
                        env={"ARYX_EMBED_PROVIDER": "nonsense"}) == "gemini-embedding-001"   # = auto


def test_an_empty_embed_endpoint_counts_as_not_set(monkeypatch):
    """`ARYX_EMBED_ENDPOINT=` (present but empty) used to switch the cloud embeddings off."""
    assert _embed_model(monkeypatch, ollama_up=False,
                        env={"ARYX_EMBED_ENDPOINT": ""}) == "gemini-embedding-001"
    assert _embed_model(monkeypatch, ollama_up=False,
                        env={"ARYX_EMBED_ENDPOINT": "http://ollama:11434"}) == "nomic-embed-text"


def test_the_reachability_probe_is_cached_and_never_raises(monkeypatch):
    from aryx.api import admin_api

    calls = []

    def boom(*_a, **_k):
        calls.append(1)
        raise OSError("no route")

    monkeypatch.setattr(admin_api.urllib.request, "urlopen", boom)
    admin_api._REACHABLE.clear()
    assert admin_api._ollama_reachable("http://nowhere:11434") is False
    assert admin_api._ollama_reachable("http://nowhere:11434") is False     # cached
    assert calls == [1]


# ---- ARYX_EMBED_MODEL names the OLLAMA model; it must not reach a cloud provider (review #56) ----

def test_the_documented_ollama_model_name_is_never_sent_to_gemini(monkeypatch, caplog):
    """A Gemini setup that keeps ARYX_EMBED_MODEL=nomic-embed-text and has no Ollama used to
    send that name to Gemini: every request failed and the chunks loaded without vectors."""
    for mode in ("auto", "cloud"):
        env = {"ARYX_EMBED_MODEL": "nomic-embed-text"}
        if mode == "cloud":
            env["ARYX_EMBED_PROVIDER"] = "cloud"
        assert _embed_model(monkeypatch, ollama_up=False, env=env) == "gemini-embedding-001"


def test_a_cloud_model_override_is_honoured_only_when_the_cloud_is_chosen_explicitly(monkeypatch):
    env = {"ARYX_EMBED_MODEL": "text-embedding-3-small"}
    # auto: the override is the Ollama setting, so the provider's own model is used
    assert _embed_model(monkeypatch, ollama_up=False, env=env) == "gemini-embedding-001"
    # explicit cloud: the operator named a model for the provider
    assert _embed_model(monkeypatch, ollama_up=False,
                        env={**env, "ARYX_EMBED_PROVIDER": "cloud"}) == "text-embedding-3-small"


@pytest.mark.parametrize("name", ["nomic-embed-text", "nomic-embed-text:latest", "mxbai-embed-large",
                                  "all-minilm", "snowflake-arctic-embed", "bge-m3", "BGE-large"])
def test_known_local_model_names_are_ignored_on_the_cloud_path(monkeypatch, caplog, name):
    from aryx.api import admin_api

    monkeypatch.setenv("ARYX_EMBED_MODEL", name)
    with caplog.at_level("WARNING"):
        assert admin_api._cloud_embed_model("cloud") == ""
    assert "Ollama model" in caplog.text and name in caplog.text


def test_ollama_itself_still_uses_the_model_name(monkeypatch):
    """The override still drives the Ollama path, which is what it is for."""
    from aryx import llm_runtime
    from aryx.api import admin_api

    for key in ("ARYX_EMBED_ENDPOINT", "ARYX_EMBED_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ARYX_EMBED_MODEL", "mxbai-embed-large")
    monkeypatch.setattr(admin_api, "_ollama_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(llm_runtime, "status", lambda: {
        "provider": "google", "endpoint": "https://g/v1beta/openai",
        "menial_model": "m", "answer_model": "m"})
    assert admin_api._local_broker().doc_embed_model_id == "mxbai-embed-large"
