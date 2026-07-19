"""File ingest API: upload up to 50 files (JSON/CSV/PDF/DOCX/PPTX/images).

Limits: 20 MB per file, 50 MB total per request, max 50 files.
JSON/CSV go through the standard entity pipeline.
Documents (PDF/DOCX/PPTX/images) go through chunk→PII→embed→extract→entity.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from aryx.api.admin_api import _local_broker
from aryx.brief import merge_with_context
from aryx.config import get_settings
from aryx.connectors.csv_source import CsvConnector
from aryx.connectors.doc_router import DocumentRouterConnector
from aryx.connectors.json_source import JsonConnector
from aryx.pipeline.doc_discovery import _infer_type, infer_fk_links
from aryx.pipeline.orchestrate import link_entities, run_pipeline
from aryx.store.chunk_store import ChunkStore
from aryx.store.job_store import JobStore
from aryx.store.migrate import apply_migrations
from aryx.workspaces import WorkspaceStore

logger = logging.getLogger(__name__)

_DATA_EXTS = {".json", ".csv"}
_DOC_EXTS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".rtf",
             ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
_ALL = _DATA_EXTS | _DOC_EXTS
_MAX_FILE = 20 * 1024 * 1024
_MAX_TOTAL = 50 * 1024 * 1024
_MAX_FILES = 50


def _save_tmp(data: bytes, suffix: str) -> Path:
    tmp = NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)


def _colvals(data: bytes, suffix: str) -> dict[str, Any]:
    """Return {colvals: {column -> [values]}} for FK discovery ({} on failure)."""
    if suffix == ".json":
        return {"colvals": {}}
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8", "ignore")))
        cols: dict[str, list[str]] = {}
        for row in reader:
            for k, v in row.items():
                if k is not None:
                    cols.setdefault(k, []).append((v or "").strip())
        return {"colvals": cols}
    except csv.Error:
        return {"colvals": {}}


def _workspace_context(dsn: str, workspace_id: int) -> str:
    """Serialize a workspace's onboarding brief + context for type inference.

    Threaded into ``_infer_type`` so an entity the user explicitly named in the
    onboarding goal is honoured — without it the row type was guessed from the
    CSV header alone, ignoring the goal entirely.
    """
    try:
        store = WorkspaceStore(dsn)
        try:
            ws = next((w for w in store.list_all()
                       if int(w["id"]) == int(workspace_id)), None)
        finally:
            store.close()
    except Exception:  # noqa: BLE001 — context is best-effort, never block ingest
        logger.debug("workspace context load failed", exc_info=True)
        return ""
    if not ws:
        return ""
    return merge_with_context(ws.get("brief"), ws.get("context") or "").strip()


def _norm_tokens(text: str) -> list[str]:
    """Word tokens: lowercased, split on non-alphanumerics, plural-stripped.

    So ``contract_number``, "Contract Numbers", and "contract number" all
    normalise to ``[contract, number]`` — the drafter naturalises the goal's
    tokens (e.g. writes "Line Numbers") and this maps them back to the column.
    """
    out: list[str] = []
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        if len(t) > 3 and t.endswith("s"):
            t = t[:-1]
        out.append(t)
    return out


def _columns_in_context(context: str, cols: list[str]) -> list[str]:
    """Return the file columns the user explicitly named in the goal/brief.

    Users often state the identity outright ("a Contract is identified by its
    contract_number ... every line by its contract_number together with its
    line_number"). When the goal names real columns, those ARE the match key
    the user asked for — honour them instead of trusting the LLM's guess, which
    is unreliable and here keyed on an unrelated column (APC).

    A column is "named" when EVERY word of its (normalised) name appears in the
    context — so ``line_number`` matches "Line Numbers" but a ``Line Number
    Sorter`` column (needs "sorter" too) does not. Returned in the order the
    columns appear in the goal, so a composite key keeps the stated order
    (contract_number before line_number).
    """
    if not context or not cols:
        return []
    ctx_tokens = _norm_tokens(context)
    ctx_set = set(ctx_tokens)
    first_at: dict[str, int] = {}
    for i, t in enumerate(ctx_tokens):
        first_at.setdefault(t, i)
    found: list[tuple[int, str]] = []
    for col in cols:
        parts = _norm_tokens(col)
        if parts and all(p in ctx_set for p in parts):
            found.append((min(first_at[p] for p in parts), col))
    found.sort(key=lambda t: t[0])
    return [c for _, c in found]


def _run_files(items: list[tuple[bytes, str]], ontology_type: str,
               match_keys: list[str], fk_links: list[dict], job_id: str,
               workspace_id: int = 1) -> None:
    settings = get_settings()
    jobs = JobStore(settings.rdb_dsn)
    broker = _local_broker()
    # The onboarding goal/brief — so explicitly-named entities are honoured.
    context = _workspace_context(settings.rdb_dsn, workspace_id)
    try:
        data_files = [(d, n) for d, n in items if Path(n).suffix.lower() in _DATA_EXTS]
        doc_files = [(d, n) for d, n in items if Path(n).suffix.lower() in _DOC_EXTS]
        # Per-file plans feed cross-file FK inference once everything has landed.
        plans: list[dict[str, Any]] = []
        for data, name in data_files:
            suffix = Path(name).suffix.lower()
            if suffix == ".json":
                connector = JsonConnector(_save_tmp(data, ".json"), system="json")
            else:
                connector = CsvConnector(data, system="csv", dataset=Path(name).stem)
            # Per-file type/key inference. A single (type, match_keys) pair
            # cannot fit a heterogeneous batch of files, and the UI default
            # ("Document" / "name") matches no real CSV column — which yields
            # empty match text and collapses every row into one entity. When
            # the caller didn't pin a concrete type, infer the row entity and
            # its identifying columns from this file's own header + sample.
            otype, keys = ontology_type, match_keys
            if not otype or otype.lower() == "document":
                plan = _infer_type(data[:800].decode("utf-8", "ignore"), name, context)
                otype, keys = plan["ontology_type"], plan["match_keys"]
                logger.info("inferred %s -> type=%s keys=%s", name, otype, keys)
            cv = _colvals(data, suffix)
            # Validate match keys against real columns. A bogus key (the LLM
            # invents one, or wrong casing) forces the whole-row fallback in
            # landed_records — which makes every row's match text huge and
            # similar, exploding pairwise scoring + adjudication into hours.
            # Repair deterministically: use the most-unique column (the natural
            # key) so matching is both fast and correct.
            cols = list(cv["colvals"].keys())
            # Honour columns the user explicitly named in the goal. If the
            # brief/context mentions real column names, those ARE the identity
            # the user asked for — use them directly (in stated order) instead
            # of the LLM's guess. This is what "take contract_number" means.
            named = _columns_in_context(context, cols)
            if named:
                logger.info("honoring goal-named match keys for %s: %s", name, named)
                keys = named
            valid = [k for k in keys if k in cols]
            if valid:
                keys = valid
            elif cols:
                best = max(cols, key=lambda c: len({v for v in cv["colvals"][c] if v}))
                logger.info("match_keys %s not columns of %s; using key '%s'",
                            keys, name, best)
                keys = [best]
            plans.append({"ontology_type": otype, **cv})
            jobs.update_stage(job_id, "Ingest", 20, f"Processing {name}")
            run_pipeline(
                connector=connector, dsn=settings.rdb_dsn,
                system=suffix.lstrip("."), dataset=Path(name).stem,
                ontology_type=otype, match_keys=keys,
                graph_url=settings.graph_url, broker=broker,
                on_progress=lambda s, p, d: jobs.update_stage(job_id, s, p, d),
                fk_links=fk_links, workspace_id=workspace_id,
            )
        # Cross-file relationships. The UI sends no fk_links, so with every
        # entity now landed, infer foreign-key edges from the files' columns
        # and materialize the ones whose values actually match, then re-project.
        if not fk_links and len(plans) >= 2:
            jobs.update_stage(job_id, "Link", 92, "Inferring relationships")
            inferred = infer_fk_links(plans)
            if inferred:
                link_entities(settings.rdb_dsn, settings.graph_url,
                              workspace_id, inferred)
        if doc_files:
            jobs.update_stage(job_id, "Documents", 50, f"Chunking {len(doc_files)} doc(s)")
            paths = [_save_tmp(d, Path(n).suffix) for d, n in doc_files]
            chunk_store = ChunkStore(settings.rdb_dsn)
            connector = DocumentRouterConnector(
                paths=paths, system="document", broker=broker,
                chunk_store=chunk_store, chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap, expected_embed_dim=settings.embed_dim,
            )
            run_pipeline(
                connector=connector, dsn=settings.rdb_dsn,
                system="document", dataset="upload",
                ontology_type=ontology_type, match_keys=match_keys,
                graph_url=settings.graph_url, broker=broker,
                on_progress=lambda s, p, d: jobs.update_stage(job_id, s, p, d),
                fk_links=fk_links, workspace_id=workspace_id,
            )
        jobs.finish(job_id, run_id=None, status="complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("file ingest failed job=%s: %s", job_id, exc, exc_info=True)
        jobs.finish(job_id, run_id=None, status="failed", error=str(exc))
    finally:
        jobs.close()


def file_ingest_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.post("/ingest/file")
    async def ingest_file(
        background_tasks: BackgroundTasks,
        files: list[UploadFile] = File(...),
        ontology_type: str = Form(...),
        match_keys: str = Form(...),
        fk_links: str = Form("[]"),
        workspace_id: int = Form(1),
    ) -> dict[str, Any]:
        if len(files) > _MAX_FILES:
            raise HTTPException(400, f"Max {_MAX_FILES} files per upload")
        items: list[tuple[bytes, str]] = []
        total = 0
        for f in files:
            data = await f.read()
            if len(data) > _MAX_FILE:
                raise HTTPException(400, f"{f.filename}: exceeds 20 MB limit")
            total += len(data)
            if total > _MAX_TOTAL:
                raise HTTPException(400, f"Total upload exceeds 50 MB limit")
            suffix = Path(f.filename or "").suffix.lower()
            if suffix not in _ALL:
                raise HTTPException(400, f"{f.filename}: unsupported type {suffix}")
            items.append((data, f.filename or f"upload{suffix}"))
        settings = get_settings()
        apply_migrations(settings.rdb_dsn)
        job_id = uuid.uuid4().hex
        jobs = JobStore(settings.rdb_dsn)
        try:
            jobs.create(job_id, "upload", f"{len(items)} file(s)", workspace_id)
        finally:
            jobs.close()
        keys = [k.strip() for k in match_keys.split(",") if k.strip()]
        links = json.loads(fk_links) if fk_links else []
        background_tasks.add_task(_run_files, items, ontology_type, keys, links, job_id, workspace_id)
        names = [n for _, n in items]
        return {"status": "queued", "job_id": job_id, "files": names, "count": len(items)}

    @router.get("/ingest/supported")
    def supported_types() -> dict[str, Any]:
        return {
            "file_types": sorted(_ALL),
            "max_files": _MAX_FILES,
            "max_file_mb": _MAX_FILE // (1024 * 1024),
            "max_total_mb": _MAX_TOTAL // (1024 * 1024),
        }

    return router
