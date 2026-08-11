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
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from aryx.api.admin_api import _local_broker
from aryx.config import get_settings
from aryx.connectors.csv_source import CsvConnector
from aryx.connectors.doc_router import DocumentRouterConnector
from aryx.connectors.json_source import JsonConnector, _flatten
from aryx.dataset.ingest import register_dataset
from aryx.pipeline.chain_jobs import run_chain_now
from aryx.pipeline.doc_discovery import _infer_type, infer_fk_links
from aryx.pipeline.downstream import intent_ready
from aryx.pipeline.orchestrate import link_entities, run_pipeline
from aryx.store.chunk_store import ChunkStore
from aryx.store.dataset_store import DatasetStore
from aryx.store.job_store import JobStore
from aryx.store.migrate import apply_migrations

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
        try:
            loaded = json.loads(data.decode("utf-8-sig"))
            rows = loaded if isinstance(loaded, list) else [loaded]
            cols: dict[str, list[str]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for k, v in _flatten(row).items():
                    if v is not None:
                        cols.setdefault(k, []).append(str(v).strip())
            return {"colvals": cols}
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
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


def _snapshot_dataset(dsn: str, workspace_id: int, data: bytes, name: str,
                      request_id: str) -> str | None:
    """C02 — register the raw upload as an immutable, versioned dataset.

    C03 (profile) and C04 (interpret) run later, gated on C01 (intent) being
    valid — see the run_downstream() call in _run_files and the backfill
    triggered from intent_api.capture.

    Returns the dataset_id when a snapshot exists (so the caller can scope the
    later graph/context steps to just this run's datasets), else None.
    Best-effort: registration may never block ingestion.
    """
    try:
        store = DatasetStore(dsn, workspace_id)
        try:
            result = register_dataset(data=data, file_name=name,
                                      request_id=request_id, store=store)
        finally:
            store.close()
    except Exception:  # noqa: BLE001 — snapshot is additive, never block ingest
        logger.warning("dataset snapshot failed file=%s", name, exc_info=True)
        return None
    if result.ingestion_status not in ("accepted", "duplicate") or not result.dataset_version:
        return None
    return result.dataset_id


def _brief_context(workspace_id: int) -> str:
    """Render the workspace brief as steering context for extraction.

    THE foundational contract: everything the user answered in the Brief
    (domain, aim, scope, roles) steers what the extractors look for. An
    empty brief returns "" and extraction runs generic.
    """
    try:
        from aryx.workspaces import WorkspaceStore
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            ws = next((w for w in store.list_all()
                       if w["id"] == workspace_id), None)
        finally:
            store.close()
        b = (ws or {}).get("brief") or {}
        parts = []
        if b.get("domain"):
            parts.append(f"Domain: {b['domain']}")
        if b.get("aim"):
            parts.append(f"Aim: {b['aim']}")
        if b.get("scope"):
            parts.append(f"Scope: {b['scope']}")
        if b.get("objectives"):
            parts.append("Objectives: " + "; ".join(b["objectives"]))
        if b.get("questions"):
            parts.append("Questions the graph must answer: "
                         + "; ".join(b["questions"]))
        return "\n".join(parts)
    except Exception as exc:  # noqa: BLE001 — steering is best-effort
        logger.warning("brief context unavailable ws=%s: %s",
                       workspace_id, exc)
        return ""


def _run_files(items: list[tuple[bytes, str]], ontology_type: str,
               match_keys: list[str], fk_links: list[dict], job_id: str,
               workspace_id: int = 1, request_id: str = "",
               context: str = "") -> None:
    settings = get_settings()
    jobs = JobStore(settings.rdb_dsn)
    broker = _local_broker()
    context = _brief_context(workspace_id)
    # Replay standing human corrections into the extraction context.
    try:
        from aryx.api.corrections_api import corrections_digest
        digest = corrections_digest(workspace_id)
        if digest:
            context = (context + "\n\nStanding corrections from the user "
                       "(obey these exactly):\n" + digest).strip()
    except Exception:  # noqa: BLE001 — corrections are best-effort steering
        logger.debug("corrections digest unavailable", exc_info=True)
    if context:
        logger.info("ingest steered by brief+corrections ws=%s (%d chars)",
                    workspace_id, len(context))
    try:
        data_files = [(d, n) for d, n in items if Path(n).suffix.lower() in _DATA_EXTS]
        doc_files = [(d, n) for d, n in items if Path(n).suffix.lower() in _DOC_EXTS]
        total_entities = 0
        # Per-file plans feed cross-file FK inference once everything has landed.
        plans: list[dict[str, Any]] = []
        snapshotted_ids: set[str] = set()  # datasets touched THIS run (for C07)
        for data, name in data_files:
            suffix = Path(name).suffix.lower()
            # C02 — snapshot the raw upload before transform.
            snapped = _snapshot_dataset(settings.rdb_dsn, workspace_id, data, name,
                                        request_id)
            if snapped:
                snapshotted_ids.add(snapped)
            if suffix == ".json":
                connector = JsonConnector(
                    _save_tmp(data, ".json"), system="json",
                    dataset=Path(name).stem,
                )
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
            summary = run_pipeline(
                connector=connector, dsn=settings.rdb_dsn,
                system=suffix.lstrip("."), dataset=Path(name).stem,
                ontology_type=otype, match_keys=keys,
                graph_url=settings.graph_url, broker=broker,
                on_progress=lambda s, p, d: jobs.update_stage(job_id, s, p, d),
                fk_links=fk_links, workspace_id=workspace_id,
            )
            total_entities += int(summary.get("entities") or 0)
        # Cross-file relationships. The UI sends no fk_links, so with every
        # entity now landed, infer foreign-key edges from the files' columns
        # and materialize the ones whose values actually match, then re-project.
        if not fk_links and len(plans) >= 2:
            jobs.update_stage(job_id, "Link", 92, "Inferring relationships")
            inferred = infer_fk_links(plans)
            if inferred:
                link_entities(settings.rdb_dsn, settings.graph_url,
                              workspace_id, inferred)
        # C03-C07 onward — the zero-click auto-chain (context -> planner ->
        # execution -> dashboard). Gated on C01: deferred until a valid
        # intent exists for the workspace, at which point intent_api.capture
        # (or a Brief save) starts the chain itself. Called inline, not via
        # BackgroundTasks — _run_files already runs as its own background
        # task, so there's no live request/BackgroundTasks to enqueue onto.
        if snapshotted_ids:
            if intent_ready(settings.rdb_dsn, workspace_id):
                run_chain_now(settings.rdb_dsn, workspace_id, broker=broker)
            else:
                logger.info(
                    "intent not yet captured ws=%s; deferring auto-chain for %d dataset(s)",
                    workspace_id, len(snapshotted_ids),
                )
        if doc_files:
            jobs.update_stage(job_id, "Documents", 40, f"Chunking {len(doc_files)} doc(s)")
            paths = [_save_tmp(d, Path(n).suffix) for d, n in doc_files]
            chunk_store = ChunkStore(settings.rdb_dsn)
            connector = DocumentRouterConnector(
                paths=paths, system="document", broker=broker,
                chunk_store=chunk_store, chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap, expected_embed_dim=settings.embed_dim,
                context=context,
            )
            # Extract once (chunk→PII→embed→LLM mentions), then land PER
            # DISCOVERED TYPE — so entities carry their real types (Ticket,
            # Agent, WorkflowStage…) in the graph and the ontology, instead
            # of everything collapsing into "Document".
            mentions = list(connector.extract())
            by_type: dict[str, list[Any]] = {}
            for m in mentions:
                t = str(m.payload.get("type") or "Document").strip() or "Document"
                by_type.setdefault(t, []).append(m)
            from aryx.api import ontology_browse
            from aryx.connectors.records_source import RecordsConnector
            type_names = sorted(by_type, key=lambda t: -len(by_type[t]))
            for idx, otype in enumerate(type_names):
                try:
                    ontology_browse.add_type(otype, ["name"], "approved",
                                             source="doc-discovery",
                                             workspace_id=workspace_id)
                except Exception:  # noqa: BLE001 — type may already exist
                    pass
                jobs.update_stage(job_id, "Documents",
                                  50 + int(idx * 40 / max(len(type_names), 1)),
                                  f"Landing {len(by_type[otype])} × {otype}")
                summary = run_pipeline(
                    connector=RecordsConnector(by_type[otype]),
                    dsn=settings.rdb_dsn,
                    system="document", dataset=otype,
                    ontology_type=otype, match_keys=["name"],
                    graph_url=settings.graph_url, broker=broker,
                    # Relate on the LAST landing only: _relate scans the whole
                    # workspace, so one pass covers cross-type edges too.
                    relate=(idx == len(type_names) - 1), max_pairs=150,
                    on_progress=lambda s, p, d: jobs.update_stage(job_id, s, p, d),
                    fk_links=fk_links, workspace_id=workspace_id,
                )
                total_entities += int(summary.get("entities") or 0)
        # Honest failure beats fake success: files were processed but NOT ONE
        # entity landed — almost always the extraction model returning
        # unusable output (still downloading, wrong provider, bad key).
        if items and total_entities == 0:
            jobs.finish(
                job_id, run_id=None, status="failed",
                error="No entities were extracted from the upload. The "
                      "language model returned nothing usable — check the "
                      "model in Settings (is it ready?) and retry.")
            return
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
        context: str = Form(...),
        fk_links: str = Form("[]"),
        workspace_id: int = Form(1),
        request_id: str = Form(""),
    ) -> dict[str, Any]:
        if not context.strip():
            raise HTTPException(
                400, "context is required — describe what these files "
                     "contain so mapping and extraction can use it")
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
        background_tasks.add_task(_run_files, items, ontology_type, keys, links,
                                  job_id, workspace_id, request_id, context)
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
