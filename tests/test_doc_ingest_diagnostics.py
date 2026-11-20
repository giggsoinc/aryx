"""PDF ingest must say where it failed, say why a document was skipped, and not
throw a document away because the embed service is down.

Prod ran the LLM on Gemini without an Ollama container: PDFs were chunked, then
embedding failed with "Name or service not known" and the document was dropped,
so the upload ended with "No entities were extracted" and nobody could tell why.
"""
from __future__ import annotations

import logging
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path

import pytest

from aryx.connectors import doc_router
from aryx.models import RawRecord, SourceRef


class _Store:
    """Minimal ChunkStore double that records what was saved."""

    def __init__(self) -> None:
        self.saved_embeddings: list = []

    def upsert_document(self, **_kw) -> int:
        return 1

    def save_chunks(self, _doc_id, chunks) -> list[int]:
        return list(range(1, len(chunks) + 1))

    def save_embeddings(self, ids, embeddings) -> None:
        self.saved_embeddings.append((ids, embeddings))


def _record() -> RawRecord:
    return RawRecord(source=SourceRef(system="document", dataset="d", record_id="r"),
                     payload={"type": "Person", "name": "Ada"})


@pytest.fixture()
def pdf(tmp_path: Path) -> Path:
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


def _wire(monkeypatch, embed, pages=None, extract=None) -> None:
    """Stub parsing/chunking/PII/extract; ``embed`` stands in for embed_chunks."""
    page_list = pages if pages is not None else [(1, "some text")]
    monkeypatch.setattr(
        doc_router, "_connector_for",
        lambda _p, _skip=False, _ocr=None: type("C", (), {"extract_pages": lambda s: page_list})())
    monkeypatch.setattr(doc_router, "chunk_pages", lambda *a, **k: ["c1", "c2"])
    monkeypatch.setattr(doc_router, "screen_chunks", lambda c: c)
    monkeypatch.setattr(doc_router, "embed_chunks", embed)
    monkeypatch.setattr(doc_router, "extract_mentions",
                        extract or (lambda chunks, _b, context="", on_progress=None, stats=None:
                                    [_record()]))


def _ingest(pdf: Path, store: _Store, skip_tables: bool = False) -> list[RawRecord]:
    return doc_router.ingest_document(pdf, "document", broker=object(), chunk_store=store,
                                      chunk_size=1000, chunk_overlap=100,
                                      expected_embed_dim=768, skip_tables=skip_tables)


# ---- an unreachable embed service no longer drops the document --------------

def test_unreachable_embed_service_still_extracts_entities(monkeypatch, pdf, caplog):
    def _boom(*_a, **_k):
        raise OSError("<urlopen error [Errno -2] Name or service not known>")

    _wire(monkeypatch, _boom)
    store = _Store()
    with caplog.at_level(logging.INFO, logger=doc_router.logger.name):
        records = _ingest(pdf, store)
    assert len(records) == 1, "entities must still be extracted"
    assert store.saved_embeddings == [], "no vectors to save when embedding failed"
    assert any("embedding skipped" in r.message and "a.pdf" in r.message
               for r in caplog.records)
    assert any("[step 5/6]" in r.message and "vectors=0" in r.message
               for r in caplog.records)


def test_dimension_mismatch_drops_vectors_but_keeps_the_document(monkeypatch, pdf):
    def _mismatch(*_a, **_k):
        raise RuntimeError("embed dim mismatch: model='m' produced 1024, expected 768")

    _wire(monkeypatch, _mismatch)
    store = _Store()
    assert len(_ingest(pdf, store)) == 1
    assert store.saved_embeddings == [], "mixed-dim vectors must never be stored"


def test_working_embed_service_still_saves_vectors(monkeypatch, pdf):
    _wire(monkeypatch, lambda *_a, **_k: ["v1", "v2"])
    store = _Store()
    assert len(_ingest(pdf, store)) == 1
    assert store.saved_embeddings == [([1, 2], ["v1", "v2"])]


# ---- 1. step-by-step logging --------------------------------------------------

def test_every_step_is_logged_in_order(monkeypatch, pdf, caplog):
    _wire(monkeypatch, lambda *_a, **_k: ["v1", "v2"])
    with caplog.at_level(logging.INFO, logger=doc_router.logger.name):
        _ingest(pdf, _Store())
    steps = [r.message.split("]")[0] + "]" for r in caplog.records if "[step " in r.message]
    assert steps == [f"[step {n}/6]" for n in range(1, 7)]


def test_a_failure_names_the_step_it_happened_in(monkeypatch, pdf, caplog):
    def _extract_boom(*_a, **_k):
        raise TimeoutError("The read operation timed out")

    _wire(monkeypatch, lambda *_a, **_k: ["v1"], extract=_extract_boom)
    with caplog.at_level(logging.INFO, logger=doc_router.logger.name):
        with pytest.raises(TimeoutError):
            _ingest(pdf, _Store())
    failed = [r.message for r in caplog.records if "ingest failed" in r.message]
    assert failed and "at step 6/6" in failed[0] and "a.pdf" in failed[0]
    assert "entities extracted" not in failed[0] and "embedded" in failed[0]   # last good step


# ---- 3. a document with no text says so ----------------------------------------

def test_a_document_with_no_text_raises_a_clear_error(monkeypatch, pdf):
    _wire(monkeypatch, lambda *_a, **_k: [], pages=[(1, ""), (2, "   \n")])
    with pytest.raises(doc_router.NoReadableText, match="No readable text.*a.pdf"):
        _ingest(pdf, _Store())


def test_a_tables_only_pdf_is_not_a_no_text_error(monkeypatch, pdf):
    """With the tables read separately, the prose of a PDF may legitimately be empty."""
    _wire(monkeypatch, lambda *_a, **_k: [], pages=[])
    records = _ingest(pdf, _Store(), skip_tables=True)
    assert [r.payload for r in records] == [{"type": "Person", "name": "Ada"}]


def test_the_connector_reports_why_a_document_was_skipped(monkeypatch, pdf):
    _wire(monkeypatch, lambda *_a, **_k: [], pages=[(1, "")])
    conn = doc_router.DocumentRouterConnector(
        paths=[pdf], system="document", broker=object(), chunk_store=_Store())
    assert list(conn.extract()) == []
    assert len(conn.problems) == 1 and "No readable text" in conn.problems[0]


# ---- 2. an honest timeout message ----------------------------------------------

def _timeout(monkeypatch, pdf, budget: float) -> list[str]:
    def _raise(*_a, **_k):
        raise FuturesTimeout()

    monkeypatch.setattr(doc_router, "_ingest_with_timeout", _raise)
    monkeypatch.setattr(doc_router, "_PER_DOC_TIMEOUT", budget)
    conn = doc_router.DocumentRouterConnector(
        paths=[pdf], system="document", broker=object(), chunk_store=_Store())
    list(conn.extract())
    return conn.problems


def test_a_quick_timeout_is_blamed_on_the_inner_call_not_the_budget(monkeypatch, pdf):
    problems = _timeout(monkeypatch, pdf, budget=300)       # raised after ~0 s
    assert "a step timed out" in problems[0] and "before the 300s limit" in problems[0]
    assert "took longer" not in problems[0]


def test_a_timeout_that_used_the_whole_budget_is_blamed_on_the_budget(monkeypatch, pdf):
    problems = _timeout(monkeypatch, pdf, budget=0)         # any elapsed time >= budget
    assert "took longer than the 0s limit" in problems[0]
    assert "ARYX_PER_DOC_TIMEOUT" in problems[0]


# ---- the time limit grows with the page count --------------------------------

def test_a_long_pdf_gets_a_longer_budget_than_a_short_one(monkeypatch, tmp_path):
    monkeypatch.setattr(doc_router, "_PER_DOC_TIMEOUT", 300.0)
    monkeypatch.setattr(doc_router, "_PER_PAGE_TIMEOUT", 30.0)
    pages = {"short.pdf": 3, "long.pdf": 40}
    monkeypatch.setattr(doc_router, "_pdf_pages", lambda p: pages.get(p.name, 0))
    assert doc_router._budget(tmp_path / "short.pdf") == 300.0      # never below the base
    assert doc_router._budget(tmp_path / "long.pdf") == 1200.0      # 40 pages x 30 s
    assert doc_router._budget(tmp_path / "notes.docx") == 300.0     # unknown page count


def test_the_page_count_of_a_real_pdf_and_of_a_broken_one(tmp_path):
    import fitz
    good = tmp_path / "g.pdf"
    doc = fitz.open()
    for _ in range(4):
        doc.new_page()
    doc.save(str(good))
    bad = tmp_path / "b.pdf"
    bad.write_bytes(b"%PDF-1.4 not really")
    assert doc_router._pdf_pages(good) == 4
    assert doc_router._pdf_pages(bad) == 0                          # falls back to the base
    assert doc_router._pdf_pages(tmp_path / "x.docx") == 0


# ---- tables-only: the text stays searchable, no entities come from it --------

def test_tables_only_keeps_chunks_and_embeddings_but_skips_the_model(monkeypatch, pdf, caplog):
    def _must_not_run(*_a, **_k):
        raise AssertionError("extract_mentions must not run in tables-only mode")

    _wire(monkeypatch, lambda *_a, **_k: ["v1", "v2"], extract=_must_not_run)
    store = _Store()
    with caplog.at_level(logging.INFO, logger=doc_router.logger.name):
        records = doc_router.ingest_document(
            pdf, "document", broker=object(), chunk_store=store, chunk_size=1000,
            chunk_overlap=100, expected_embed_dim=768, extract_entities=False)
    assert records == []
    assert store.saved_embeddings == [([1, 2], ["v1", "v2"])]       # still searchable
    assert any("entity extraction skipped" in r.message for r in caplog.records)


def test_the_connector_skips_extraction_only_for_the_paths_it_is_told(monkeypatch, tmp_path):
    seen: list[tuple[str, bool]] = []

    def spy(path, *args, **kw):
        seen.append((path.name, args[-2]))               # (..., on_progress, extract_entities, ocr)
        return []

    monkeypatch.setattr(doc_router, "_ingest_with_timeout", spy)
    tabled, plain = tmp_path / "t.pdf", tmp_path / "p.pdf"
    for f in (tabled, plain):
        f.write_bytes(b"x")
    conn = doc_router.DocumentRouterConnector(
        paths=[tabled, plain], system="document", broker=None, chunk_store=None,
        extract_entities_paths=frozenset({plain}))         # tables-only: only p.pdf is read by the model
    list(conn.extract())
    assert seen == [("t.pdf", False), ("p.pdf", True)]
    seen.clear()
    list(doc_router.DocumentRouterConnector(
        paths=[tabled], system="document", broker=None, chunk_store=None).extract())
    assert seen == [("t.pdf", True)]                       # default: every document
