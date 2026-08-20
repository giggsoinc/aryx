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


def _columns(data: bytes, suffix: str) -> set[str]:
    """Field names present in one data file (header only — no value scan)."""
    if suffix == ".json":
        try:
            loaded = json.loads(data.decode("utf-8-sig"))
            rows = loaded if isinstance(loaded, list) else [loaded]
            row = next((r for r in rows if isinstance(r, dict)), {})
            return set(_flatten(row).keys())
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return set()
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8", "ignore")))
        return set(reader.fieldnames or [])
    except csv.Error:
        return set()


def _shape_mismatches(
    items: list[tuple[bytes, str]], file_types: dict[str, str],
) -> list[str]:
    """Names of data files whose columns barely overlap the batch's first file.

    A file pinned in `file_types` is excluded from comparison — the caller
    already resolved its type explicitly, so a shape difference there is
    intentional, not the silent-collapse bug this guards against.
    """
    candidates = [(d, n) for d, n in items
                  if Path(n).suffix.lower() in _DATA_EXTS and n not in file_types]
    if len(candidates) < 2:
        return []
    col_sets = [(_columns(d, Path(n).suffix.lower()), n) for d, n in candidates]
    base_cols, base_name = col_sets[0]
    mismatched = [name for cols, name in col_sets[1:]
                  if base_cols and cols
                  and len(base_cols & cols) / len(base_cols | cols) < 0.5]
    return [base_name, *mismatched] if mismatched else []


def _parse_file_types(raw: str) -> dict[str, str]:
    """Parse the file_types form field into {filename: ontology_type}.

    Raises HTTPException(400) on malformed JSON, a non-object, or any
    non-string key/value — a wrong type here would otherwise flow silently
    into the ingest pipeline and only surface as a confusing background-job
    failure much later, rather than a clear rejection at upload time.
    """
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "file_types must be JSON: {filename: ontology_type}")
    if not isinstance(parsed, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()):
        raise HTTPException(
            400, "file_types must be a JSON object of {filename: ontology_type} strings")
    return parsed


def _resolve_batch_ontology_type(
    items: list[tuple[bytes, str]], ontology_type: str, file_types: dict[str, str],
) -> str:
    """Decide whether the caller's shared ontology_type is safe to apply to
    every un-pinned file in this batch.

    A single type cannot fit files of different shapes (that is exactly what
    produced the workspace-39 incident: 3 CSVs of 3 real kinds all forced
    into "Customer"). Rather than rejecting the upload and pushing the
    caller to work out per-file types themselves, drop the shared type back
    to "" for a mismatched batch — the empty/'Document' path already infers
    a type per file from its own columns, which is the classification the
    caller actually wants here.
    """
    if not ontology_type or ontology_type.strip().lower() == "document":
        return ontology_type
    mismatched = _shape_mismatches(items, file_types)
    if mismatched:
        logger.warning(
            "ontology_type=%r does not fit every file in this batch "
            "(mismatched shapes: %s) — auto-detecting a type per file instead",
            ontology_type, ", ".join(mismatched))
        return ""
    return ontology_type


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
    """Render the customer brief as steering context for extraction.

    THE foundational contract: the brief the customer wrote BEFORE upload
    (domain, aim, objectives, scope, roles, proof questions) steers what the
    extractors look for. Uses the canonical `aryx.brief` serialiser so this
    matches every other brief consumer, and folds in the free-text workspace
    context (which carries the planned entity types) as a supplement.

    An empty brief returns "" and extraction runs generic — the soft gate.

    Deliberately reads `brief` off `list_all()` rather than via
    `get_understanding()`: this endpoint does not run apply_migrations (the
    MCP `ingest_file` tool calls it directly, and may be the first call a
    fresh deployment ever sees), and `brief` has existed since migration
    0016 while `data_understanding`/`brief_source` only arrive in 0044.
    Depending on the newer columns here would make an un-migrated database
    fall into the except branch and silently drop brief grounding that this
    path used to have.
    """
    try:
        from aryx.brief import merge_with_context
        from aryx.workspaces import WorkspaceStore
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            ws = next((w for w in store.list_all()
                       if w["id"] == workspace_id), None)
        finally:
            store.close()
        ws = ws or {}
        return merge_with_context(ws.get("brief") or {},
                                  str(ws.get("context") or ""))
    except Exception as exc:  # noqa: BLE001 — steering is best-effort
        logger.warning("brief context unavailable ws=%s: %s",
                       workspace_id, exc)
        return ""


def _run_files(items: list[tuple[bytes, str]], ontology_type: str,
               match_keys: list[str], fk_links: list[dict], job_id: str,
               workspace_id: int = 1, request_id: str = "",
               graph_plan: dict | None = None,
               file_types: dict[str, str] | None = None) -> None:
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
    else:
        # Soft gate: the brief step is skippable, so this is a warning, not
        # a block. Extraction still runs — just without customer grounding.
        logger.warning("ingest ungrounded ws=%s — no customer brief captured "
                       "before upload; extraction runs generic", workspace_id)
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
            # A per-file pin (file_types) wins outright — the caller already
            # resolved this file's type explicitly, so none of the shared-type
            # or inference fallbacks below should second-guess it.
            pinned = (file_types or {}).get(name)
            if pinned:
                otype = pinned
            # Prefer smart graph_plan (data-first understand) over generic Document.
            if not pinned and graph_plan and (not otype or otype.lower() == "document"):
                from aryx.pipeline.smart_understand import primary_type_and_keys
                otype, keys = primary_type_and_keys(graph_plan, name)
                logger.info("plan %s -> type=%s keys=%s", name, otype, keys)
            if not pinned and (not otype or otype.lower() == "document"):
                plan = _infer_type(data[:800].decode("utf-8", "ignore"), name, context)
                otype, keys = plan["ontology_type"], plan["match_keys"]
                logger.info("inferred %s -> type=%s keys=%s", name, otype, keys)
            # Seed Model canvas with primary type
            try:
                from aryx.api import ontology_browse
                ontology_browse.add_type(
                    otype, list(keys)[:8] or ["name"], "approved",
                    source="ingest", workspace_id=workspace_id)
            except Exception:  # noqa: BLE001
                pass
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

            def _progress(s: str, p: int, d: str, _jid: str = job_id) -> None:
                # Heartbeats only touch stage (no event spam); others log both.
                if "still working" in (d or ""):
                    jobs.heartbeat(_jid, s, p, d)
                else:
                    jobs.update_stage(_jid, s, p, d)

            summary = run_pipeline(
                connector=connector, dsn=settings.rdb_dsn,
                system=suffix.lstrip("."), dataset=Path(name).stem,
                ontology_type=otype, match_keys=keys,
                graph_url=settings.graph_url, broker=broker,
                on_progress=_progress,
                on_run_id=lambda rid, _jid=job_id: jobs.attach_run(_jid, rid),
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
        # Data-first plan: dimension entities (Merchant, Category, …) + edges
        if graph_plan and data_files:
            jobs.update_stage(job_id, "Dimensions", 93, "Materializing plan dimensions")
            try:
                from aryx.pipeline.dimension_materialize import materialize_dimensions
                nrel = materialize_dimensions(
                    dsn=settings.rdb_dsn, graph_url=settings.graph_url,
                    workspace_id=workspace_id, broker=broker,
                    graph_plan=graph_plan, colvals_by_file=plans,
                )
                logger.info("dimension materialize rels=%s", nrel)
            except Exception as exc:  # noqa: BLE001
                logger.warning("dimension materialize failed: %s", exc)
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
        # C03-C07 onward — the zero-click auto-chain (context -> planner ->
        # execution -> dashboard). Gated on C01: deferred until a valid
        # intent exists for the workspace, at which point intent_api.capture
        # (or a Brief save) starts the chain itself. Runs after every other
        # data-shaping step (dimensions, documents) so it sees the finished
        # batch. Called inline, not via BackgroundTasks — _run_files already
        # runs as its own background task, so there's no live request/
        # BackgroundTasks to enqueue onto.
        if snapshotted_ids:
            if intent_ready(settings.rdb_dsn, workspace_id):
                run_chain_now(settings.rdb_dsn, workspace_id, broker=broker)
            else:
                logger.info(
                    "intent not yet captured ws=%s; deferring auto-chain for %d dataset(s)",
                    workspace_id, len(snapshotted_ids),
                )
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
        ontology_type: str = Form("Document"),
        match_keys: str = Form("name"),
        fk_links: str = Form("[]"),
        workspace_id: int = Form(1),
        graph_plan: str = Form(""),
        file_types: str = Form(""),
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
        file_types_map = _parse_file_types(file_types)
        ontology_type = _resolve_batch_ontology_type(items, ontology_type, file_types_map)
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
        plan_obj: dict | None = None
        if graph_plan and graph_plan.strip():
            try:
                plan_obj = json.loads(graph_plan)
            except json.JSONDecodeError:
                plan_obj = None
        background_tasks.add_task(
            _run_files, items, ontology_type, keys, links, job_id, workspace_id,
            graph_plan=plan_obj, file_types=file_types_map)
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
