"""Document router: per-type connectors → chunk → PII → embed → extract (Inc 8)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

from aryx.broker import Broker
from aryx.connectors.base import Connector
from aryx.connectors.docx import DocxConnector
from aryx.connectors.image import ImageConnector, SUPPORTED_EXTENSIONS as IMAGE_EXTS
from aryx.connectors.markup import MarkupConnector
from aryx.connectors.pdf import PdfConnector
from aryx.connectors.pptx import PptxConnector
from aryx.models import RawRecord, SourceRef
from aryx.ontology.extract import extract_mentions
from aryx.pipeline.clean_text import chunk_pages
from aryx.pipeline.embed import embed_chunks
from aryx.pipeline.pii import screen_chunks
from aryx.raven_log_config import log as raven_log
from aryx.store.chunk_store import ChunkStore

logger = logging.getLogger(__name__)

_EXT_MAP: dict[str, type] = {
    ".pdf": PdfConnector,
    ".pptx": PptxConnector, ".ppt": PptxConnector,
    ".docx": DocxConnector, ".doc": DocxConnector, ".rtf": DocxConnector,
    ".xml": MarkupConnector, ".html": MarkupConnector, ".htm": MarkupConnector,
    **{ext: ImageConnector for ext in IMAGE_EXTS},
}


def _content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _connector_for(path: Path):
    cls = _EXT_MAP.get(path.suffix.lower())
    if cls is None:
        raise ValueError(f"unsupported document type: {path.suffix!r}")
    return cls(path)


# Hard wall-clock budget per document — a hang in parse / OCR / embed /
# extract is abandoned so the batch finishes. Override ARYX_PER_DOC_TIMEOUT.
_PER_DOC_TIMEOUT = float(os.environ.get("ARYX_PER_DOC_TIMEOUT", "300"))


def _ingest_with_timeout(
    path: Path, system: str, broker: Broker, chunk_store: ChunkStore,
    chunk_size: int, chunk_overlap: int, expected_embed_dim: int,
    run_pii: bool, context: str,
) -> list[RawRecord]:
    """ingest_document under a hard timeout; raises FuturesTimeout on hang.

    The pool is shut down with wait=False: `with ThreadPoolExecutor(...)` calls
    shutdown(wait=True) on exit, which blocks until the worker thread returns —
    so a hung parse/model-download held the whole batch long past the timeout
    and the FuturesTimeout handler never ran. A thread cannot be killed; we
    stop waiting for it and let the batch move on.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(
            ingest_document, path, system, broker, chunk_store,
            chunk_size, chunk_overlap, expected_embed_dim, run_pii, context,
        )
        return future.result(timeout=_PER_DOC_TIMEOUT)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def ingest_document(
    path: Path, system: str, broker: Broker, chunk_store: ChunkStore,
    chunk_size: int, chunk_overlap: int, expected_embed_dim: int,
    run_pii: bool = True, context: str = "",
) -> list[RawRecord]:
    doc_id = _content_hash(path)
    source = SourceRef(system=system, dataset=path.stem, record_id=doc_id)
    pages = list(_connector_for(path).extract_pages())
    chunks = chunk_pages(pages, source=source, doc_id=doc_id,
                         chunk_size=chunk_size, overlap=chunk_overlap)
    if run_pii:
        chunks = screen_chunks(chunks)
    doc_db_id = chunk_store.upsert_document(
        content_hash=doc_id, file_name=path.name,
        source_type=path.suffix.lstrip(".").lower(),
        byte_count=path.stat().st_size,
    )
    chunk_db_ids = chunk_store.save_chunks(doc_db_id, chunks)
    embeddings = embed_chunks(chunks, broker, expected_dim=expected_embed_dim)
    chunk_store.save_embeddings(chunk_db_ids, embeddings)
    records = extract_mentions(chunks, broker, context=context)
    logger.info("ingest_document path=%s doc_id=%s chunks=%d mentions=%d",
                path.name, doc_id[:8], len(chunks), len(records))
    return records


class DocumentRouterConnector(Connector):
    """Plugs the document pipeline into discover() via the Connector ABC."""

    def __init__(
        self, paths: list[Path], system: str, broker: Broker,
        chunk_store: ChunkStore, chunk_size: int = 1000,
        chunk_overlap: int = 100, expected_embed_dim: int = 768,
        run_pii: bool = True, context: str = "",
        display_names: dict[Path, str] | None = None,
    ) -> None:
        # Uploads are staged under random temp names; display_names maps each
        # staged path back to the user's filename for error reporting.
        self._display_names = display_names or {}
        self.failures: list[tuple[str, str]] = []  # (original filename, reason)
        self._paths = paths
        self._system = system
        self._broker = broker
        self._chunk_store = chunk_store
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._expected_embed_dim = expected_embed_dim
        self._run_pii = run_pii
        self._context = context

    def extract(self) -> Iterator[RawRecord]:
        for path in self._paths:
            try:
                yield from _ingest_with_timeout(
                    path, self._system, self._broker, self._chunk_store,
                    self._chunk_size, self._chunk_overlap,
                    self._expected_embed_dim, self._run_pii, self._context,
                )
            except FuturesTimeout:
                shown = self._display_names.get(path, path.name)
                reason = (f"took longer than {_PER_DOC_TIMEOUT:.0f}s (parse, PII, "
                          "embedding or LLM extraction — slow CPU models need a "
                          "larger ARYX_PER_DOC_TIMEOUT)")
                self.failures.append((shown, reason))
                logger.error("ingest TIMED OUT path=%s after %ss — skipping; "
                             "batch continues", shown, _PER_DOC_TIMEOUT)
                raven_log("ERROR", "document ingest timed out; batch continues",
                          criticality="P2", service="aryx-api",
                          error_code="DOC_INGEST_TIMEOUT",
                          context={"file": shown, "timeout_s": _PER_DOC_TIMEOUT,
                                   "stage": "Documents", "result": "skipped_timeout"})
            except Exception as exc:
                shown = self._display_names.get(path, path.name)
                self.failures.append((shown, f"{type(exc).__name__}: {exc}"))
                logger.error("ingest failed path=%s error=%s", shown, exc)
                raven_log("ERROR", "document ingest failed; batch continues",
                          criticality="P2", service="aryx-api",
                          error_code="DOC_INGEST_FAILED",
                          context={"file": shown, "exception": type(exc).__name__,
                                   "stage": "Documents", "result": "skipped_error"})


async def ingest_documents_parallel(
    paths: list[Path], system: str, broker: Broker, chunk_store: ChunkStore,
    chunk_size: int = 1000, chunk_overlap: int = 100,
    expected_embed_dim: int = 768, run_pii: bool = True,
) -> list[RawRecord]:
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(
            None, lambda p=path: ingest_document(
                p, system, broker, chunk_store,
                chunk_size, chunk_overlap, expected_embed_dim, run_pii,
            ),
        )
        for path in paths
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_records: list[RawRecord] = []
    for path, result in zip(paths, results):
        if isinstance(result, Exception):
            logger.error("parallel ingest failed path=%s error=%s", path.name, result)
        else:
            all_records.extend(result)
    return all_records
