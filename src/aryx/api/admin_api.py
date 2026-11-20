"""Admin API: ingestion triggers with durable per-stage job progress."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import os
import time
import urllib.request

import psycopg
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from aryx import llm_runtime
from aryx.broker import Broker, ModelSpec, Registry, TokenGovernor
from aryx.broker.embedding import cloud_embed_config
from aryx.config import get_settings
from aryx.connectors.postgres import PostgresConnector, sample_colvals
from aryx.pipeline.orchestrate import run_pipeline
from aryx.resolution.field_shape import resolve_match_keys
from aryx.store.job_store import JobStore
from aryx.job_cancel import run_cancellable
from aryx.store.migrate import apply_migrations


def _embed_mode() -> str:
    """ARYX_EMBED_PROVIDER: ``auto`` (default), ``cloud`` or ``ollama``."""
    mode = os.environ.get("ARYX_EMBED_PROVIDER", "auto").strip().lower()
    return mode if mode in ("auto", "cloud", "ollama") else "auto"


# Embedding models that only exist on Ollama (or other local servers): sent to a cloud
# provider they fail. ARYX_EMBED_MODEL=nomic-embed-text is the documented Ollama setting.
_LOCAL_EMBED_PREFIXES = ("nomic-embed", "mxbai-embed", "all-minilm", "snowflake-arctic-embed",
                         "bge-", "granite-embedding")


def _cloud_embed_model(mode: str) -> str:
    """The ARYX_EMBED_MODEL to send to a cloud provider, or "" for its default model.

    ARYX_EMBED_MODEL names the OLLAMA model. It is honoured on the cloud path only when
    the cloud provider was chosen explicitly (ARYX_EMBED_PROVIDER=cloud) and the name is
    not a known local model; otherwise a Gemini setup that merely keeps the documented
    ``ARYX_EMBED_MODEL=nomic-embed-text`` would send that name to Gemini, every embedding
    request would fail and the chunks would load without vectors.
    """
    name = os.environ.get("ARYX_EMBED_MODEL", "").strip()
    if not name or mode != "cloud":
        return ""
    if name.lower().startswith(_LOCAL_EMBED_PREFIXES):
        logger.warning("ARYX_EMBED_MODEL=%s is an Ollama model; the cloud provider's own "
                       "embedding model is used instead", name)
        return ""
    return name


_REACHABLE: dict[str, tuple[float, bool]] = {}


def _ollama_reachable(endpoint: str, ttl: float = 60.0) -> bool:
    """True when an Ollama service answers at ``endpoint`` (cached for ``ttl`` seconds)."""
    now = time.monotonic()
    cached = _REACHABLE.get(endpoint)
    if cached and now - cached[0] < ttl:
        return cached[1]
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/api/tags", timeout=1.5):  # noqa: S310
            ok = True
    except Exception:  # noqa: BLE001 - unreachable, refused, DNS failure, timeout
        ok = False
    _REACHABLE[endpoint] = (now, ok)
    return ok


def _local_broker() -> Broker:
    """Pipeline broker — honours Settings → LLM Provider (live, no restart).

    Reads aryx.llm_runtime.status() so the doc ingest pipeline + the Ask API
    share ONE config. Switching provider/model in the Settings panel now
    drives both. Embeddings stay on local Ollama (nomic-embed-text) — text
    similarity is provider-agnostic for the demo path.
    """
    cfg = llm_runtime.status()
    provider = str(cfg.get("provider") or "ollama")
    endpoint = str(cfg.get("endpoint") or "http://ollama:11434")
    menial = str(cfg.get("menial_model") or "qwen3.5:0.8b")
    answer = str(cfg.get("answer_model") or "lfm2.5-thinking:latest")
    is_ollama = provider == "ollama"
    api_key_ref = None if is_ollama else llm_runtime._KEY_REF
    embed_model = os.environ.get("ARYX_EMBED_MODEL", "nomic-embed-text")
    explicit_endpoint = os.environ.get("ARYX_EMBED_ENDPOINT", "").strip()   # empty = not set
    embed_endpoint = explicit_endpoint or (
        endpoint if is_ollama else "http://ollama:11434")
    registry = Registry()
    for name, tier in ((menial, "cheap"), (answer, "frontier")):
        registry.add(ModelSpec(name=name, provider=provider, tier=tier,
                               local=is_ollama, endpoint=endpoint,
                               api_key_ref=api_key_ref))
    # A cloud LLM (Gemini) can embed document chunks on the same provider, so the
    # deployment needs no Ollama service. That is never a silent switch: an explicit
    # ARYX_EMBED_ENDPOINT, or ARYX_EMBED_PROVIDER=ollama, keeps Ollama; =cloud forces
    # the provider; the default ("auto") uses the provider only when no Ollama
    # answers, so a deployment with a working Ollama keeps its own embeddings.
    doc_embed = None
    mode = _embed_mode()
    if not is_ollama and not explicit_endpoint and mode != "ollama" and (
            mode == "cloud" or not _ollama_reachable(embed_endpoint)):
        doc_embed = cloud_embed_config(
            provider, endpoint, api_key_ref, get_settings().embed_dim,
            _cloud_embed_model(mode))
    # One line per job, so a brief Ollama restart that sent one upload to the cloud model
    # (the "auto" decision is cached for up to a minute) is easy to spot afterwards.
    logger.info("document embeddings: %s (ARYX_EMBED_PROVIDER=%s, %s)",
                doc_embed["model"] if doc_embed else embed_model, mode,
                "provider" if doc_embed else "ollama")
    return Broker(
        registry, TokenGovernor({}),
        secrets=llm_runtime._RuntimeSecrets(),
        embed_config={"model": embed_model, "endpoint": embed_endpoint},
        doc_embed_config=doc_embed,
    )

logger = logging.getLogger(__name__)


class FkLink(BaseModel):
    source_type: str
    source_attr: str
    target_type: str
    target_attr: str
    name: str


class IngestDbRequest(BaseModel):
    table: str
    ontology_type: str
    match_keys: str
    system: str = "postgresql"
    key_column: str = "id"
    fk_links: list[FkLink] = []
    workspace_id: int = 1


def _run_db(req: IngestDbRequest, job_id: str) -> None:
    """Background: ingest one Postgres table end-to-end into the graph."""
    settings = get_settings()
    jobs = JobStore(settings.rdb_dsn)
    try:
        connector = PostgresConnector(
            dsn=settings.rdb_dsn, table=req.table,
            key_column=req.key_column, batch_size=settings.batch_size,
        )
        keys = [k.strip() for k in req.match_keys.split(",") if k.strip()]
        colvals = sample_colvals(settings.rdb_dsn, req.table)
        keys, transactional = resolve_match_keys(keys, colvals)
        summary = run_pipeline(
            connector=connector, dsn=settings.rdb_dsn,
            system=req.system, dataset=req.table,
            ontology_type=req.ontology_type,
            match_keys=keys,
            broker=_local_broker(),
            on_progress=lambda stage, pct, detail: jobs.update_stage(job_id, stage, pct, detail),
            fk_links=[link.model_dump() for link in req.fk_links],
            workspace_id=req.workspace_id,
            skip_resolution=transactional,
        )
        jobs.finish(job_id, run_id=summary.get("run_id"), status="complete")
    except Exception as exc:  # noqa: BLE001 — record failure for the dashboard
        logger.warning("ingest failed job=%s: %s", job_id, exc)
        jobs.finish(job_id, run_id=None, status="failed", error=str(exc))
    finally:
        jobs.close()


def admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.post("/ingest/db")
    def ingest_db(req: IngestDbRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
        settings = get_settings()
        apply_migrations(settings.rdb_dsn)
        jobs = JobStore(settings.rdb_dsn)
        job_id = uuid.uuid4().hex
        try:
            jobs.archive_old(30)
            jobs.create(job_id, req.system, req.table, req.workspace_id)
        finally:
            jobs.close()
        background_tasks.add_task(run_cancellable, _run_db, settings.rdb_dsn, job_id,
                                  req.workspace_id, req, job_id)
        return {"status": "queued", "job_id": job_id, "table": req.table}

    @router.get("/runs")
    def list_runs() -> list[dict[str, Any]]:
        settings = get_settings()
        with psycopg.connect(settings.rdb_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT run_id, source_system, source_dataset, status, "
                    "record_count, started_at, finished_at "
                    "FROM aryx_run ORDER BY run_id DESC LIMIT 50"
                )
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]

    return router
