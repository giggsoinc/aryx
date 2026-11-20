"""Behaviour added in answer to the review of #56."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

from aryx.connectors import doc_router
from aryx.connectors.doc_tables import DocTable, _to_table, merge_continued
from aryx.envnum import env_number
from aryx.models import DocumentChunk, SourceRef
from aryx.ontology import extract


# ---- tables: only a table that continues on the NEXT page is merged ----------------

def test_two_different_tables_with_the_same_header_stay_apart():
    """Two sections that both start "ID | Description" are two tables."""
    first = DocTable(["ID", "Description"], [["A1", "x"], ["A2", "y"]])
    second = DocTable(["ID", "Description"], [["B1", "z"]])
    out = merge_continued([first, second], pages=[2, 9])          # pages 2 and 9
    assert [len(t.rows) for t in out] == [2, 1]


def test_a_table_split_across_a_page_break_is_still_joined():
    first = DocTable(["ID", "Description"], [["A1", "x"]])
    second = DocTable(["ID", "Description"], [["A2", "y"]])
    out = merge_continued([first, second], pages=[2, 3])
    assert len(out) == 1 and [r[0] for r in out[0].rows] == ["A1", "A2"]


def test_a_table_on_the_same_page_with_the_same_header_is_a_different_table():
    a = DocTable(["ID", "Description"], [["A1", "x"]])
    b = DocTable(["ID", "Description"], [["B1", "y"]])
    assert len(merge_continued([a, b], pages=[4, 4])) == 2


def test_without_page_numbers_only_the_table_right_before_is_joined():
    a = DocTable(["ID", "Name"], [["1", "a"]])
    b = DocTable(["ID", "Name"], [["2", "b"]])
    other = DocTable(["X", "Y"], [["p", "q"]])
    c = DocTable(["ID", "Name"], [["3", "c"]])
    out = merge_continued([a, b, other, c])
    assert [len(t.rows) for t in out] == [2, 1, 1]               # c is not glued back onto a/b


# ---- wrapped rows: only a sparse row with no id is a continuation --------------------

def test_a_real_record_that_only_lacks_an_id_is_not_glued_to_the_row_above():
    grid = [["ID", "Name", "Role", "Dept"],
            ["E1", "Ada", "Engineer", "R&D"],
            ["E2", "Grace", "Admiral", "Navy"],
            ["", "Linus", "Maintainer", "Kernel"],              # a whole record, id missing
            ["E4", "Alan", "Logician", "Math"],
            ["E5", "Edsger", "Scientist", "CS"]]
    table = _to_table(grid)
    assert [r[1] for r in table.rows] == ["Ada", "Grace", "Linus", "Alan", "Edsger"]
    assert table.rows[2][0] == ""                                # kept as its own record


def test_a_sparse_row_with_no_id_is_still_the_second_line_of_the_row_above():
    grid = [["ID", "Requirement", "Priority"],
            ["BR-1", "The bot accepts a change spec and the", "Must"],
            ["", "RuleBook XML as inputs", ""],
            ["BR-2", "A human approves every plan", "Must"],
            ["BR-3", "Each step is verified", "Must"],
            ["BR-4", "Prior state can be restored", "Must"],
            ["BR-5", "Every action is recorded", "Must"],
            ["BR-6", "The bot runs as a service", "Should"]]
    table = _to_table(grid)
    assert len(table.rows) == 6
    assert table.rows[0][1] == "The bot accepts a change spec and the RuleBook XML as inputs"


# ---- extraction failures reach the job error --------------------------------------------

def _chunks(n=3):
    src = SourceRef(system="document", dataset="d", record_id="doc")
    return [DocumentChunk(doc_id="d" * 64, chunk_index=i, text=f"text {i}", source=src)
            for i in range(n)]


def test_extract_mentions_reports_how_many_chunks_failed_and_why(monkeypatch):
    monkeypatch.setattr(extract, "_ATTEMPTS", 1)
    monkeypatch.setattr(extract, "_WORKERS", 1)

    def fake(_b, _t, _s, user, _schema):
        if '"chunk_index": 1' in user:
            raise TimeoutError("The read operation timed out")
        return {"mentions": []}

    monkeypatch.setattr(extract, "complete_json", fake)
    stats: dict = {}
    extract.extract_mentions(_chunks(3), broker=None, stats=stats)
    assert stats["failed"] == 1 and "timed out" in stats["last_error"]


class _Store:
    def upsert_document(self, **_kw): return 1
    def save_chunks(self, _d, chunks): return list(range(1, len(chunks) + 1))
    def save_embeddings(self, *_a): pass


def _wire(monkeypatch, stats_out):
    monkeypatch.setattr(doc_router, "_connector_for", lambda *_a, **_k: type(
        "C", (), {"extract_pages": lambda s: [(1, "some text")]})())
    monkeypatch.setattr(doc_router, "chunk_pages", lambda *a, **k: ["c1", "c2"])
    monkeypatch.setattr(doc_router, "screen_chunks", lambda c: c)
    monkeypatch.setattr(doc_router, "embed_chunks", lambda *_a, **_k: [])

    def fake_extract(chunks, _b, context="", on_progress=None, stats=None):
        stats.update(stats_out)
        return []

    monkeypatch.setattr(doc_router, "extract_mentions", fake_extract)


def test_when_every_part_fails_the_job_error_says_so(monkeypatch, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    _wire(monkeypatch, {"failed": 2, "last_error": "TimeoutError: The read operation timed out"})
    conn = doc_router.DocumentRouterConnector(
        paths=[pdf], system="document", broker=object(), chunk_store=_Store())
    assert list(conn.extract()) == []
    assert len(conn.problems) == 1
    assert "could not read any part of the text" in conn.problems[0]
    assert "2 parts failed" in conn.problems[0] and "timed out" in conn.problems[0]


def test_when_only_some_parts_fail_the_document_still_succeeds(monkeypatch, tmp_path, caplog):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"x")
    _wire(monkeypatch, {"failed": 1, "last_error": "x"})
    conn = doc_router.DocumentRouterConnector(
        paths=[pdf], system="document", broker=object(), chunk_store=_Store())
    with caplog.at_level(logging.INFO, logger=doc_router.logger.name):
        list(conn.extract())
    assert conn.problems == []
    assert any("failed_parts=1" in r.message for r in caplog.records)


# ---- settings: a typo never stops a module from importing --------------------------------

@pytest.mark.parametrize("raw,expected", [("5", 5), ("  7 ", 7), ("three", 3), ("", 3), ("0", 3), ("-2", 3)])
def test_an_integer_setting_falls_back_on_a_typo(monkeypatch, raw, expected):
    monkeypatch.setenv("ARYX_TEST_SETTING", raw)
    assert env_number("ARYX_TEST_SETTING", 3, int, minimum=1) == expected


def test_a_float_setting_and_an_unset_one(monkeypatch):
    monkeypatch.setenv("ARYX_TEST_SETTING", "12.5")
    assert env_number("ARYX_TEST_SETTING", 300.0, float, minimum=1) == 12.5
    monkeypatch.delenv("ARYX_TEST_SETTING")
    assert env_number("ARYX_TEST_SETTING", 300.0, float, minimum=1) == 300.0
    monkeypatch.setenv("ARYX_TEST_SETTING", "soon")
    assert env_number("ARYX_TEST_SETTING", 300.0, float, minimum=1) == 300.0


def test_the_modules_import_with_a_broken_environment(monkeypatch):
    import importlib

    from aryx.connectors import doc_router as dr
    from aryx.ontology import extract as ex
    from aryx.pipeline import enrich as en

    for name in ("ARYX_EXTRACT_WORKERS", "ARYX_EXTRACT_ATTEMPTS", "ARYX_RELATE_WORKERS",
                 "ARYX_RELATE_BUDGET_S", "ARYX_PER_DOC_TIMEOUT", "ARYX_PER_PAGE_TIMEOUT"):
        monkeypatch.setenv(name, "not-a-number")
    try:
        for module in (ex, en, dr):
            importlib.reload(module)
        assert ex._WORKERS == 3 and en._WORKERS == 6 and dr._PER_DOC_TIMEOUT == 300.0
    finally:
        for name in ("ARYX_EXTRACT_WORKERS", "ARYX_EXTRACT_ATTEMPTS", "ARYX_RELATE_WORKERS",
                     "ARYX_RELATE_BUDGET_S", "ARYX_PER_DOC_TIMEOUT", "ARYX_PER_PAGE_TIMEOUT"):
            monkeypatch.delenv(name, raising=False)
        for module in (ex, en, dr):
            importlib.reload(module)


# ---- the shared token counter is safe from several threads ---------------------------------

def test_the_token_governor_does_not_lose_charges_from_worker_threads():
    from aryx.broker.governor import TokenGovernor

    gov = TokenGovernor({})

    def work():
        for _ in range(2000):
            gov.charge("cheap", 1)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert gov._spent["cheap"] == 16000


# ---- the time limit really releases the batch (Raven review M1) ---------------------------

def test_a_stuck_document_is_abandoned_at_the_budget_and_does_not_hold_the_batch(monkeypatch, tmp_path):
    """The real _ingest_with_timeout, with a document that hangs: the timeout must reach the
    caller at about the budget, not after the stuck work finishes on its own."""
    import time
    from concurrent.futures import TimeoutError as FuturesTimeout

    release = threading.Event()

    def hangs(*_a, **_k):
        release.wait(30)                       # a stalled model call
        return []

    monkeypatch.setattr(doc_router, "ingest_document", hangs)
    monkeypatch.setattr(doc_router, "_PER_DOC_TIMEOUT", 0.3)
    monkeypatch.setattr(doc_router, "_PER_PAGE_TIMEOUT", 0.0)
    doc = tmp_path / "a.docx"
    doc.write_bytes(b"x")
    began = time.monotonic()
    try:
        with pytest.raises(FuturesTimeout):
            doc_router._ingest_with_timeout(doc, "document", object(), object(), 1000, 100,
                                            768, True, "")
        took = time.monotonic() - began
    finally:
        release.set()                          # let the abandoned thread end
    assert took < 2.0, f"the timeout was held for {took:.1f}s by the stuck work"


def test_the_batch_carries_on_to_the_next_document_after_a_hang(monkeypatch, tmp_path):
    import time

    release = threading.Event()
    calls: list[str] = []

    def fake(path, *_a, **_k):
        calls.append(path.name)
        if path.name == "a.docx":
            release.wait(30)
        return []

    monkeypatch.setattr(doc_router, "ingest_document", fake)
    monkeypatch.setattr(doc_router, "_PER_DOC_TIMEOUT", 0.3)
    monkeypatch.setattr(doc_router, "_PER_PAGE_TIMEOUT", 0.0)
    paths = [tmp_path / "a.docx", tmp_path / "b.docx"]
    for p in paths:
        p.write_bytes(b"x")
    conn = doc_router.DocumentRouterConnector(
        paths=paths, system="document", broker=object(), chunk_store=_Store())
    began = time.monotonic()
    try:
        list(conn.extract())
        took = time.monotonic() - began
    finally:
        release.set()
    assert calls == ["a.docx", "b.docx"] and took < 3.0
    assert len(conn.problems) == 1 and "a.docx" in conn.problems[0]


# ---- which embedding side "auto" picked is logged for every job (Raven review L2) ---------

def test_the_embedding_choice_is_logged_once_per_job(monkeypatch, caplog):
    from aryx import llm_runtime
    from aryx.api import admin_api

    for name in ("ARYX_EMBED_ENDPOINT", "ARYX_EMBED_MODEL", "ARYX_EMBED_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_runtime, "status", lambda: {
        "provider": "google", "endpoint": "https://g/v1beta/openai",
        "menial_model": "m", "answer_model": "m"})
    for up, expect in ((False, "gemini-embedding-001"), (True, "nomic-embed-text")):
        monkeypatch.setattr(admin_api, "_ollama_reachable", lambda *_a, **_k: up)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=admin_api.logger.name):
            admin_api._local_broker()
        lines = [r.message for r in caplog.records if "document embeddings" in r.message]
        assert len(lines) == 1 and expect in lines[0] and "ARYX_EMBED_PROVIDER=auto" in lines[0]
