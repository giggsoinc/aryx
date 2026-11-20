"""Document router: per-type connectors → chunk → PII → embed → extract (Inc 8)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

from aryx.broker import Broker
from aryx.connectors.base import Connector
from aryx.envnum import env_number
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


def _connector_for(path: Path, skip_tables: bool = False, ocr=None):
    cls = _EXT_MAP.get(path.suffix.lower())
    if cls is None:
        raise ValueError(f"unsupported document type: {path.suffix!r}")
    if cls is PdfConnector:
        return cls(path, skip_tables=skip_tables, ocr=ocr)
    return cls(path)


# Hard wall-clock budget per document — a hang in parse / OCR / embed /
# extract is abandoned so the batch finishes. Override ARYX_PER_DOC_TIMEOUT.
_PER_DOC_TIMEOUT = float(env_number("ARYX_PER_DOC_TIMEOUT", 300.0, float, minimum=1))
# ...but a long PDF needs longer than a short one: each page costs model time, so
# the budget grows with the page count (never below ARYX_PER_DOC_TIMEOUT).
_PER_PAGE_TIMEOUT = float(env_number("ARYX_PER_PAGE_TIMEOUT", 30.0, float, minimum=0))


def _pdf_pages(path: Path) -> int:
    """Page count of a PDF (0 for anything else, or a file that cannot be opened)."""
    if path.suffix.lower() != ".pdf":
        return 0
    try:
        import fitz  # pymupdf

        with fitz.open(str(path)) as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001 - the real error surfaces when the file is read
        return 0


def _budget(path: Path) -> float:
    """Wall-clock seconds this document may take: grows with its page count."""
    return max(_PER_DOC_TIMEOUT, _pdf_pages(path) * _PER_PAGE_TIMEOUT)


def _ingest_with_timeout(
    path: Path, system: str, broker: Broker, chunk_store: ChunkStore,
    chunk_size: int, chunk_overlap: int, expected_embed_dim: int,
    run_pii: bool, context: str, skip_tables: bool = False,
    on_progress: Callable[[int, int, int], None] | None = None,
    extract_entities: bool = True, ocr=None,
) -> list[RawRecord]:
    """ingest_document under a hard timeout; raises FuturesTimeout on hang.

    The pool is shut down WITHOUT waiting (``wait=False``): a ``with`` block would wait for
    the stuck call to finish before the timeout reached the caller, so one hung document
    (a stalled model call or download) would hold the whole batch and the time limit would
    only show after the hang ended on its own. The abandoned thread cannot be killed; it
    runs on in the background and is left behind, and the batch carries on.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        ingest_document, path, system, broker, chunk_store,
        chunk_size, chunk_overlap, expected_embed_dim, run_pii, context,
        skip_tables, on_progress, extract_entities, ocr,
    )
    try:
        return future.result(timeout=_budget(path))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


class NoReadableText(Exception):
    """The document yielded no text at all (a scan, or an empty file)."""


_STEPS = 6


def _embed_best_effort(chunks: list, broker: Broker, expected_dim: int, path: Path) -> list:
    """Embed the chunks, or return [] when the embed service is unavailable.

    Embeddings only power semantic search over document text. Entity
    extraction does not need them, so a missing or unreachable embed service
    must not throw away the whole document. A dimension mismatch also lands
    here: the vectors are dropped rather than stored, so mixed dims never
    enter the store.
    """
    try:
        return embed_chunks(chunks, broker, expected_dim=expected_dim)
    except Exception as exc:  # noqa: BLE001 - any embed failure is non-fatal
        logger.warning(
            "embedding skipped path=%s (%s: %s) - entities are still "
            "extracted; semantic search over this document is unavailable "
            "until an embed model is reachable (ARYX_EMBED_ENDPOINT)",
            path.name, type(exc).__name__, exc)
        return []


def _no_text_message(path: Path, ocr) -> str:
    """Why a document has no text, and what to do about it."""
    base = f"No readable text was found in {path.name}. It may be a scanned image."
    if ocr is None:
        return (base + " Upload a text-based version, or turn on OCR (ARYX_OCR=auto; "
                "needs a Gemini or OpenAI key, and the page images are sent to that provider).")
    errors = getattr(ocr, "errors", [])
    if errors:
        return (base + f" OCR is on but the model could not read the page ({errors[-1]}). "
                "Check that the configured model accepts images.")
    return base + " OCR is on and read nothing from it."


def ingest_document(
    path: Path, system: str, broker: Broker, chunk_store: ChunkStore,
    chunk_size: int, chunk_overlap: int, expected_embed_dim: int,
    run_pii: bool = True, context: str = "", skip_tables: bool = False,
    on_progress: Callable[[int, int, int], None] | None = None,
    extract_entities: bool = True, ocr=None,
) -> list[RawRecord]:
    started = time.monotonic()
    step, what = 0, "reading pages"

    def done(n: int, label: str, detail: str) -> None:
        """Log a finished step, and remember which one runs next."""
        nonlocal step, what
        logger.info("[step %d/%d] %s  %s  path=%s (%.1fs)", n, _STEPS, label, detail,
                    path.name, time.monotonic() - started)
        step, what = n, label

    try:
        doc_id = _content_hash(path)
        source = SourceRef(system=system, dataset=path.stem, record_id=doc_id)
        pages = list(_connector_for(path, skip_tables, ocr).extract_pages())
        done(1, "pages read", f"pages={len(pages)}")
        if not skip_tables and not any((text or "").strip() for _, text in pages):
            raise NoReadableText(_no_text_message(path, ocr))
        chunks = chunk_pages(pages, source=source, doc_id=doc_id,
                             chunk_size=chunk_size, overlap=chunk_overlap)
        done(2, "chunked", f"chunks={len(chunks)}")
        if run_pii:
            chunks = screen_chunks(chunks)
        done(3, "PII screened", f"chunks={len(chunks)}")
        doc_db_id = chunk_store.upsert_document(
            content_hash=doc_id, file_name=path.name,
            source_type=path.suffix.lstrip(".").lower(),
            byte_count=path.stat().st_size,
        )
        chunk_db_ids = chunk_store.save_chunks(doc_db_id, chunks)
        done(4, "saved", f"chunk_ids={len(chunk_db_ids)}")
        embeddings = _embed_best_effort(chunks, broker, expected_embed_dim, path)
        if embeddings:
            chunk_store.save_embeddings(chunk_db_ids, embeddings)
        done(5, "embedded", f"vectors={len(embeddings)}" if embeddings
             else "vectors=0 (skipped, see warning above)")
        if extract_entities:
            stats: dict = {}
            records = extract_mentions(chunks, broker, context=context,
                                       on_progress=on_progress, stats=stats)
            failed = int(stats.get("failed", 0))
            if chunks and failed == len(chunks):
                # Every part failed: say so in the job error, not "the model returned nothing".
                raise RuntimeError(
                    f"the language model could not read any part of the text ({failed} parts "
                    f"failed; last error: {stats.get('last_error') or 'unknown'})")
            done(6, "entities extracted",
                 f"chunks={len(chunks)} mentions={len(records)} failed_parts={failed}")
        else:
            records = []
            done(6, "entity extraction skipped", "tables-only: the text stays searchable")
    except NoReadableText:
        raise
    except Exception as exc:
        logger.error("ingest failed path=%s at step %d/%d (after: %s) %.1fs in: %s: %s",
                     path.name, step + 1, _STEPS, what, time.monotonic() - started,
                     type(exc).__name__, exc)
        raise
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
        skip_table_paths: frozenset[Path] = frozenset(),
        on_progress: Callable[[int, int, int], None] | None = None,
        extract_entities_paths: frozenset[Path] | None = None,
        ocr=None,
    ) -> None:
        self._ocr = ocr
        self._extract_entities_paths = extract_entities_paths   # None = every document
        self._on_progress = on_progress
        self._paths = paths
        self.problems: list[str] = []   # why a document was skipped, for the job's error
        self._skip_table_paths = skip_table_paths
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
            began = time.monotonic()
            try:
                yield from _ingest_with_timeout(
                    path, self._system, self._broker, self._chunk_store,
                    self._chunk_size, self._chunk_overlap,
                    self._expected_embed_dim, self._run_pii, self._context,
                    path in self._skip_table_paths, self._on_progress,
                    self._extract_entities_paths is None
                    or path in self._extract_entities_paths,
                    self._ocr,
                )
            except FuturesTimeout:
                # The same TimeoutError comes from the outer per-document budget
                # AND from an inner call (one slow Gemini request): the elapsed
                # time says which, so the message does not blame the wrong one.
                elapsed = time.monotonic() - began
                budget = _budget(path)
                if elapsed >= budget * 0.95:
                    msg = (f"{path.name} took longer than the {budget:.0f}s limit for "
                           "this document (ARYX_PER_DOC_TIMEOUT / ARYX_PER_PAGE_TIMEOUT).")
                else:
                    msg = (f"{path.name}: a step timed out after {elapsed:.0f}s, well "
                           f"before the {budget:.0f}s limit for this document - see "
                           "the 'ingest failed ... at step' log line for which one.")
                logger.error("ingest TIMED OUT path=%s - %s skipping; batch continues",
                             path.name, msg)
                self.problems.append(msg)
            except NoReadableText as exc:
                logger.warning("ingest skipped path=%s: %s", path.name, exc)
                self.problems.append(str(exc))
            except Exception as exc:
                logger.error("ingest failed path=%s error=%s", path.name, exc)
                self.problems.append(f"{path.name}: {exc}")


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
