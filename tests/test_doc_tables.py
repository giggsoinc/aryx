"""PDF / DOCX tables are read as rows, not flattened into prose.

Plain-text extraction kept a few cells of an employee table and lost the rest
(4 of 20 people). Every table now becomes a header + rows and is ingested as a
CSV; a table split across pages (repeated header) is one table.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import docx
import fitz  # pymupdf
import pytest

from aryx.connectors import doc_router
from aryx.connectors.doc_tables import (
    DocTable, extract_tables, merge_continued, tables_as_csv_files,
)
from aryx.connectors.pdf import PdfConnector
from aryx.models import RawRecord, SourceRef

HEADER = ["Emp ID", "Name", "Dept"]
ROWS = [["E1", "Arjun Mehta", "D01"], ["E2", "Priya Nair", "D01"],
        ["E3", "Rahul Iyer", "D02"], ["E4", "Sneha Kulkarni", "D02"]]


def _draw_table(page, top: float, rows: list[list[str]]) -> None:
    """Draw a ruled grid with text, which is what find_tables detects."""
    col_w, row_h, left = 120, 24, 50
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            rect = fitz.Rect(left + c * col_w, top + r * row_h,
                             left + (c + 1) * col_w, top + (r + 1) * row_h)
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            page.insert_text((rect.x0 + 4, rect.y1 - 8), text, fontsize=10)


def _pdf(tmp_path: Path, pages: list[list[list[str]]], intro: str = "") -> Path:
    doc = fitz.open()
    for rows in pages:
        page = doc.new_page()
        if intro:
            page.insert_text((50, 40), intro, fontsize=11)
        _draw_table(page, 80, rows)
    path = tmp_path / "t.pdf"
    doc.save(str(path))
    doc.close()
    return path


def _docx_bytes(tmp_path: Path) -> bytes:
    document = docx.Document()
    document.add_paragraph("Staff list")
    table = document.add_table(rows=1, cols=3)
    for cell, text in zip(table.rows[0].cells, HEADER):
        cell.text = text
    for row in ROWS:
        for cell, text in zip(table.add_row().cells, row):
            cell.text = text
    path = tmp_path / "t.docx"
    document.save(str(path))
    return path.read_bytes()


def test_pdf_table_rows_are_extracted(tmp_path):
    tables = extract_tables(_pdf(tmp_path, [[HEADER] + ROWS]).read_bytes(), ".pdf")
    assert len(tables) == 1
    assert tables[0].header == HEADER
    assert tables[0].rows == ROWS


def test_table_split_across_pages_is_merged_without_the_repeated_header(tmp_path):
    pdf = _pdf(tmp_path, [[HEADER] + ROWS[:2], [HEADER] + ROWS[2:]])
    tables = extract_tables(pdf.read_bytes(), ".pdf")
    assert len(tables) == 1
    assert tables[0].rows == ROWS


def test_docx_table_rows_are_extracted(tmp_path):
    tables = extract_tables(_docx_bytes(tmp_path), ".docx")
    assert len(tables) == 1
    assert tables[0].header == HEADER and tables[0].rows == ROWS


def test_docx_text_extractor_never_saw_table_cells(tmp_path):
    """Why DOCX tables were lost entirely before this change."""
    from aryx.connectors.docx import _extract_docx
    path = tmp_path / "t.docx"
    path.write_bytes(_docx_bytes(tmp_path))
    assert "Arjun Mehta" not in _extract_docx(path)


def test_unusable_input_yields_no_tables(tmp_path):
    assert extract_tables(b"not a pdf", ".pdf") == []
    assert extract_tables(b"plain", ".txt") == []
    plain = fitz.open()
    plain.new_page().insert_text((50, 50), "just a paragraph, no table")
    assert extract_tables(plain.tobytes(), ".pdf") == []


def test_csv_round_trip_keeps_commas_and_quotes():
    table = DocTable(["Name", "Skills"], [["A", 'Python, "SQL"']])
    rows = list(csv.DictReader(io.StringIO(table.to_csv().decode())))
    assert rows == [{"Name": "A", "Skills": 'Python, "SQL"'}]


def test_blank_and_repeated_headers_are_made_unique():
    from aryx.connectors.doc_tables import _to_table
    table = _to_table([["ID", "", "ID"], ["1", "x", "y"]])
    assert table.header == ["ID", "column_2", "ID_2"]


def test_multiline_header_cells_are_flattened():
    from aryx.connectors.doc_tables import _to_table
    table = _to_table([["Emp ID", "Manager\nID"], ["E1", "E0"]])
    assert table.header == ["Emp ID", "Manager ID"]


def test_merge_only_joins_identical_headers():
    a = DocTable(["A", "B"], [["1", "2"]])
    b = DocTable(["a", "b"], [["3", "4"]])
    c = DocTable(["A", "C"], [["5", "6"]])
    merged = merge_continued([a, b, c])
    assert [m.rows for m in merged] == [[["1", "2"], ["3", "4"]], [["5", "6"]]]


def test_tables_become_named_csv_uploads(tmp_path):
    pdf = _pdf(tmp_path, [[HEADER] + ROWS]).read_bytes()
    files, with_tables = tables_as_csv_files([(pdf, "staff.pdf"), (b"x", "notes.txt")])
    assert [n for _, n in files] == ["staff_table1.csv"]
    assert with_tables == {"staff.pdf"}
    assert list(csv.DictReader(io.StringIO(files[0][0].decode())))[1]["Name"] == "Priya Nair"


def test_skip_tables_drops_table_text_but_keeps_the_prose(tmp_path):
    pdf = _pdf(tmp_path, [[HEADER] + ROWS], intro="HR note: Ananya is on leave.")
    kept = "\n".join(t for _, t in PdfConnector(pdf, skip_tables=True).extract_pages())
    full = "\n".join(t for _, t in PdfConnector(pdf).extract_pages())
    assert "Arjun Mehta" in full and "Arjun Mehta" not in kept
    assert "Ananya is on leave" in kept


def test_router_only_skips_tables_for_the_files_that_were_ingested_as_rows(tmp_path):
    pdf = _pdf(tmp_path, [[HEADER] + ROWS])
    assert doc_router._connector_for(pdf, skip_tables=True)._skip_tables is True
    assert doc_router._connector_for(pdf)._skip_tables is False
    seen: list[bool] = []
    original = doc_router._ingest_with_timeout

    def spy(*args, **kw):
        seen.append(args[-4])          # (..., skip_tables, on_progress, extract_entities, ocr)
        return []

    doc_router._ingest_with_timeout = spy
    try:
        other = tmp_path / "o.pdf"
        other.write_bytes(b"x")
        conn = doc_router.DocumentRouterConnector(
            paths=[pdf, other], system="document", broker=None, chunk_store=None,
            skip_table_paths=frozenset({pdf}))
        list(conn.extract())
    finally:
        doc_router._ingest_with_timeout = original
    assert seen == [True, False]


class _Jobs:
    """JobStore double: records the final status, ignores progress."""

    def __init__(self, *_a, **_k) -> None:
        self.final: dict = {}

    def __getattr__(self, _name):
        return lambda *a, **k: None

    def finish(self, _job_id, **kw) -> None:
        _Jobs.last = kw


@pytest.mark.parametrize("shared_type", ["Document", "Employee"])
def test_document_table_rows_skip_entity_resolution(monkeypatch, tmp_path, shared_type):
    """Near-identical rows (E002/2025, E003/2025) must not be fuzzy-merged.

    Live run: 10 review rows collapsed into 1 entity until document tables were
    marked one-record-per-row.
    """
    from aryx.api import file_ingest_api as api

    reviews = [["Emp ID", "Year", "Rating"]] + [
        [f"E{i:03d}", "2025", str(3 + i % 3)] for i in range(2, 12)]
    pdf = _pdf(tmp_path, [reviews]).read_bytes()
    calls: list[dict] = []

    class _Settings:
        rdb_dsn = "postgresql://x"

    monkeypatch.setattr(api, "get_settings", lambda: _Settings())
    monkeypatch.setattr(api, "JobStore", _Jobs)
    monkeypatch.setattr(api, "_local_broker", lambda: object())
    monkeypatch.setattr(api, "_brief_context", lambda ws: "")
    monkeypatch.setattr(api, "_snapshot_dataset", lambda *a, **k: (None, False))
    monkeypatch.setattr(api, "_infer_type", lambda *a, **k: {
        "ontology_type": "PerformanceReview", "match_keys": ["Emp ID", "Year"]})
    monkeypatch.setattr(api, "run_pipeline",
                        lambda **kw: calls.append(kw) or {"entities": 10})
    monkeypatch.setattr(api, "checkpoint", lambda **kw: None)
    monkeypatch.setattr(doc_router.DocumentRouterConnector, "extract",
                        lambda self: iter(()))
    from aryx.api import ontology_browse
    monkeypatch.setattr(ontology_browse, "add_type", lambda *a, **k: None)

    api._run_files([(pdf, "reviews.pdf")], shared_type, ["name"], [], "job-1")

    table_calls = [c for c in calls if c["dataset"] == "reviews_table1"]
    assert len(table_calls) == 1
    assert table_calls[0]["skip_resolution"] is True
    # Typed from its own header, not the type shared by the whole upload.
    assert table_calls[0]["ontology_type"] == "PerformanceReview"


def test_redundant_text_mentions_are_recognised():
    from aryx.connectors.doc_tables import is_redundant_mention, table_values

    covered = {"employee": table_values(
        b"Emp ID,Name,Dept\nE1,Kavya Reddy,D02\nE2,Priya Nair,D01\n")}
    assert is_redundant_mention("Kavya Reddy", "Employee", covered)      # already a row
    assert is_redundant_mention("  kavya   REDDY ", "employee", covered)  # same, tidied
    assert is_redundant_mention("<PERSON>", "Employee", covered)          # PII placeholder
    assert is_redundant_mention("employees", "Employee", covered)         # type label
    assert is_redundant_mention("Departments", "Department", covered)
    # kept: genuinely new, a different type, or empty
    assert not is_redundant_mention("Brand New Person", "Employee", covered)
    assert not is_redundant_mention("Kavya Reddy", "Person", covered)
    assert not is_redundant_mention("Chennai", "Location", covered)
    assert not is_redundant_mention("", "Employee", covered)


def test_text_mentions_already_in_a_table_are_not_landed_twice(monkeypatch, tmp_path):
    """Live run: the prose re-added Kavya Reddy, "employees" and "<PERSON>" as extra
    Employees next to the 20 table rows."""
    from aryx.api import file_ingest_api as api
    from aryx.api import ontology_browse

    pdf = _pdf(tmp_path, [[HEADER] + ROWS], intro="Kavya Reddy heads Support.").read_bytes()
    landed: dict[str, list[str]] = {}

    def _mention(name, kind):
        return RawRecord(source=SourceRef(system="document", dataset="d", record_id=name),
                         payload={"name": name, "type": kind})

    prose = [_mention("Arjun Mehta", "Employee"), _mention("employees", "Employee"),
             _mention("<PERSON>", "Employee"), _mention("Visiting Auditor", "Employee"),
             _mention("Chennai", "Location")]

    def _pipeline(**kw):
        landed[kw["dataset"]] = [r.payload.get("name") for r in kw["connector"].extract()
                                 ] if kw["system"] == "document" else []
        return {"entities": 1}

    class _Settings:
        rdb_dsn, chunk_size, chunk_overlap, embed_dim = "postgresql://x", 1000, 100, 768

    monkeypatch.setattr(api, "get_settings", lambda: _Settings())
    monkeypatch.setattr(api, "JobStore", _Jobs)
    monkeypatch.setattr(api, "ChunkStore", lambda dsn: object())
    monkeypatch.setattr(api, "_local_broker", lambda: object())
    monkeypatch.setattr(api, "_brief_context", lambda ws: "")
    monkeypatch.setattr(api, "_snapshot_dataset", lambda *a, **k: (None, False))
    monkeypatch.setattr(api, "_infer_type", lambda *a, **k: {
        "ontology_type": "Employee", "match_keys": ["Emp ID", "Name"]})
    monkeypatch.setattr(api, "run_pipeline", _pipeline)
    monkeypatch.setattr(api, "checkpoint", lambda **kw: None)
    monkeypatch.setattr(doc_router.DocumentRouterConnector, "extract",
                        lambda self: iter(prose))
    monkeypatch.setattr(ontology_browse, "add_type", lambda *a, **k: None)

    api._run_files([(pdf, "staff.pdf")], "Employee", ["name"], [], "job-1")

    assert landed["Employee"] == ["Visiting Auditor"], landed
    assert landed["Location"] == ["Chennai"], "other types are untouched"


def test_headings_titles_and_captions_are_not_entities():
    from aryx.connectors.doc_tables import is_redundant_mention
    for name, kind in [("Employees", "Category"), ("HR notes", "Category"),
                       ("Performance reviews (2025)", "Category"),
                       ("Employee Data - Northwind", "Dataset"),
                       ("HR records", "Dataset")]:
        assert is_redundant_mention(name, kind, {}), (name, kind)
    # a real organisation named in the prose is still kept
    assert not is_redundant_mention("Northwind Radio Systems", "Organization", {})


# ---- links without an LLM ---------------------------------------------------

def test_relation_table_is_read_as_edges():
    from aryx.pipeline.relation_rows import edge_name, relation_rows
    data = b"from,predicate,to\nR-01,satisfies,G-02\nR-02,depends on,R-01\n,x,\n"
    assert relation_rows(data) == [("R-01", "satisfies", "G-02"),
                                   ("R-02", "depends on", "R-01")]
    assert edge_name("depends on") == "DEPENDS_ON"
    assert relation_rows(b"id,type,name\nR-01,Req,Login\n") is None   # a normal table
    assert relation_rows(b"from,to\nA,B\n") is None                    # no predicate


class _Store:
    """EntityStore double: a fixed list of entities, and the edges that were saved."""

    def __init__(self, entities):
        self._entities, self.saved = entities, []

    def list_entities(self):
        return self._entities

    def save_relationships(self, rels):
        self.saved = rels


def test_relation_rows_link_the_entities_they_name():
    from aryx.pipeline.relation_rows import link_relation_rows
    store = _Store([(1, "Requirement", {"ID": "R-01", "Requirement": "Login", "Priority": "High"}),
                    (3, "Goal", {"ID": "G-02", "Goal": "Faster"})])
    saved, skipped = link_relation_rows(
        store, [("R-01", "satisfies", "G-02"), ("R-01", "satisfies", "G-02"),
                ("R-01", "owns", "NOPE")])
    assert (saved, skipped) == (1, 1)                       # duplicate row dropped, unknown end skipped
    edge = store.saved[0]
    assert (edge.source_entity_id, edge.target_entity_id, edge.name) == (1, 3, "SATISFIES")
    assert edge.confidence == 1.0


def test_a_second_document_never_links_the_first_documents_entities():
    """Review #56 (1): ids like R-01 repeat between documents; only this upload's entities count."""
    from aryx.pipeline.relation_rows import link_relation_rows
    store = _Store([
        (1, "Requirement", {"ID": "R-01", "a": "x", "b": "y", "c": "z"}),   # older upload, richer
        (2, "Goal", {"ID": "G-02", "a": "x", "b": "y", "c": "z"}),
        (11, "Requirement", {"ID": "R-01", "Requirement": "Login"}),        # this upload
        (12, "Goal", {"ID": "G-02", "Goal": "Faster"}),
    ])
    saved, _ = link_relation_rows(store, [("R-01", "satisfies", "G-02")],
                                  exclude_ids=frozenset({1, 2}))
    assert saved == 1
    assert (store.saved[0].source_entity_id, store.saved[0].target_entity_id) == (11, 12)


def test_a_row_whose_id_matches_several_entities_is_skipped_not_guessed():
    from aryx.pipeline.relation_rows import link_relation_rows
    store = _Store([(1, "Requirement", {"ID": "R-01"}), (2, "Entity", {"id": "R-01"}),
                    (3, "Goal", {"ID": "G-02"})])
    saved, skipped = link_relation_rows(store, [("R-01", "satisfies", "G-02")])
    assert (saved, skipped) == (0, 1) and store.saved == []


def test_only_identifier_columns_resolve_a_link_not_any_attribute():
    from aryx.pipeline.relation_rows import link_relation_rows
    store = _Store([(1, "Employee", {"Emp ID": "E1", "Status": "Active", "Level": 1}),
                    (2, "Employee", {"Emp ID": "E2", "Status": "Active"}),
                    (3, "Team", {"name": "Platform"})])
    # "Active" and "1" are attributes, not ids: neither end resolves
    assert link_relation_rows(store, [("Active", "is", "1")]) == (0, 1)
    # an Emp ID is an identifier; a name is the fallback
    assert link_relation_rows(store, [("E1", "member of", "Platform")]) == (1, 0)
    assert store.saved[0].name == "MEMBER_OF"


def test_shared_column_name_links_child_to_parent():
    from aryx.pipeline.doc_discovery import infer_fk_links
    files = [
        {"ontology_type": "Department", "colvals": {"Dept ID": ["D1", "D2", "D3"], "Department": ["Eng", "Sup", "Sales"]}},
        {"ontology_type": "Employee", "colvals": {"Emp ID": ["E1", "E2", "E3", "E4"], "Dept ID": ["D1", "D1", "D2", "D3"]}},
        {"ontology_type": "PerformanceReview", "colvals": {"Emp ID": ["E1", "E2"], "Year": ["2025", "2025"]}},
    ]
    links = {(l["source_type"], l["source_attr"], l["target_type"], l["target_attr"])
             for l in infer_fk_links(files)}
    assert ("Employee", "Dept ID", "Department", "Dept ID") in links
    assert ("PerformanceReview", "Emp ID", "Employee", "Emp ID") in links
    assert ("Department", "Dept ID", "Employee", "Dept ID") not in links   # never backwards
    assert ("Employee", "Emp ID", "PerformanceReview", "Emp ID") not in links


def test_hyphen_line_break_inside_an_id_is_joined():
    from aryx.connectors.doc_tables import _clean
    assert _clean("STG-\nPREP") == "STG-PREP"
    assert _clean("non-\n human") == "non-human"
    assert _clean("Manager\nID") == "Manager ID"        # an ordinary wrap keeps its space


def test_a_bare_id_column_does_not_link_everything():
    from aryx.pipeline.doc_discovery import infer_fk_links
    files = [
        {"ontology_type": "Role", "colvals": {"id": ["R1", "R2", "R3", "R4"]}},
        {"ontology_type": "Requirement", "colvals": {"ID": ["R1", "R2"]}},
    ]
    assert infer_fk_links(files) == []


# ---- id / type / name catalogue tables --------------------------------------

def _catalogue():
    from aryx.connectors.doc_tables import DocTable
    return DocTable(["id", "type", "name"], [
        ["R-01", "Requirement", "Login"],          # also a row of the Requirements table
        ["ACT-ADM", "Actor", "CPQ Administrator"],
        ["ACT-REQ", "Actor", "Change Requester"],
        ["STG-PREP", "Stage", "Prepare"],
    ])


def test_catalogue_rows_are_typed_by_their_own_kind_and_duplicates_dropped():
    from aryx.connectors.doc_tables import split_catalogue
    parts = dict((k, t) for k, t in split_catalogue(_catalogue(), {"r-01"}))
    assert set(parts) == {"Actor", "Stage"}                   # Requirement row already held elsewhere
    assert [r[0] for r in parts["Actor"].rows] == ["ACT-ADM", "ACT-REQ"]


def test_a_normal_table_is_not_split():
    from aryx.connectors.doc_tables import DocTable, split_catalogue
    assert split_catalogue(DocTable(["Emp ID", "Name"], [["E1", "A"]]), set()) is None
    one_kind = DocTable(["id", "type", "name"], [["1", "Actor", "a"], ["2", "Actor", "b"]])
    assert split_catalogue(one_kind, set()) is None           # a single kind is just a table


def test_split_files_carry_their_type_in_the_name():
    from aryx.connectors.doc_tables import TYPE_SEP, pin_from_name
    assert pin_from_name(f"BRD_table10{TYPE_SEP}Actor.csv") == "Actor"
    assert pin_from_name("BRD_table2.csv") is None


def test_ids_only_listed_in_a_relation_table_still_get_their_catalogue_row(monkeypatch):
    """STG-PREP appears in the from/predicate/to table, but that table holds no record."""
    from aryx.connectors import doc_tables as dt
    tables = [
        dt.DocTable(["ID", "Requirement"], [["R-01", "Login"]]),
        _catalogue(),
        dt.DocTable(["from", "predicate", "to"], [["STG-PREP", "precedes", "R-01"]]),
    ]
    monkeypatch.setattr(dt, "extract_tables", lambda *_a: tables)
    files, _ = dt.tables_as_csv_files([(b"", "BRD.pdf")])
    names = [n for _, n in files]
    assert any(n.endswith(f"{dt.TYPE_SEP}Stage.csv") for n in names)
    assert not any(n.endswith(f"{dt.TYPE_SEP}Requirement.csv") for n in names)


def test_a_catalogue_row_with_no_kind_still_lands():
    from aryx.connectors.doc_tables import DocTable, split_catalogue
    t = DocTable(["id", "type", "name"], [["A1", "Actor", "a"], ["S1", "Stage", "s"], ["X1", "", "x"]])
    kinds = {k for k, _ in split_catalogue(t, set())}
    assert kinds == {"Actor", "Stage", "Item"}


# ---- table type guess: retry, then the header (never the file name) ----------

def test_header_names_the_type_when_the_model_is_unavailable():
    from aryx.pipeline.doc_discovery import _header_type
    assert _header_type("ID,Decision,Status\nD-1,Use X,Open\n") == {
        "ontology_type": "Decision", "match_keys": ["ID", "Decision"]}
    assert _header_type("ID,Risk,Why it matters\nR-1,a,b\n")["ontology_type"] == "Risk"
    assert _header_type("ID,Rule\nB-1,x\n")["ontology_type"] == "Rule"
    assert _header_type("Term,Meaning\nA,b\n") is None          # only generic words


def test_a_timeout_is_retried_then_the_header_decides(monkeypatch):
    from aryx.pipeline import doc_discovery as dd
    calls = []
    monkeypatch.setattr(dd.time, "sleep", lambda _s: None)

    def boom(*_a, **_k):
        calls.append(1)
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr(dd.llm_runtime, "chat", boom)
    plan = dd._infer_type("ID,Decision,Status\nD-1,x,Open\n", "BRD_table8.csv", "")
    assert len(calls) == 3                                      # tried three times
    assert plan["ontology_type"] == "Decision"                  # not "BrdTable8"


def test_a_good_answer_on_the_second_try_is_used(monkeypatch):
    from aryx.pipeline import doc_discovery as dd
    answers = iter([TimeoutError("slow"), ('{"ontology_type":"Decision","match_keys":["ID"]}', 1, 1)])

    def chat(*_a, **_k):
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(dd.llm_runtime, "chat", chat)
    assert dd._infer_type("ID,Decision\nD-1,x\n", "t.csv", "")["ontology_type"] == "Decision"


def test_file_name_is_still_the_last_resort(monkeypatch):
    from aryx.pipeline import doc_discovery as dd
    monkeypatch.setattr(dd.llm_runtime, "chat", lambda *_a, **_k: (_ for _ in ()).throw(OSError("down")))
    plan = dd._infer_type("Term,Meaning\nA,b\n", "BRD_table9.csv", "")
    assert plan["ontology_type"] == "BrdTable9"


def test_a_requirement_that_wrapped_onto_two_lines_is_one_row():
    from aryx.connectors.doc_tables import _to_table
    grid = [["ID", "Requirement", "Priority"],
            ["BR-001", "The bot applies changes", "Must"],
            ["BR-002", "The bot accepts a change spec and the", "Must"],
            ["", "RuleBook XML as inputs", ""],
            ["BR-003", "A human approves every plan", "Must"],
            ["BR-004", "Each change is verified", "Must"]]
    t = _to_table(grid)
    assert [r[0] for r in t.rows] == ["BR-001", "BR-002", "BR-003", "BR-004"]
    assert t.rows[1][1] == "The bot accepts a change spec and the RuleBook XML as inputs"
    assert t.rows[1][2] == "Must"


def test_a_table_that_leaves_the_first_column_blank_on_purpose_is_untouched():
    from aryx.connectors.doc_tables import _to_table
    grid = [["Group", "Item"], ["A", "x"], ["", "y"], ["", "z"], ["", "w"]]
    assert len(_to_table(grid).rows) == 4


def test_a_row_that_breaks_across_a_page_is_one_row():
    from aryx.connectors.doc_tables import DocTable, merge_continued
    page1 = DocTable(["ID", "Requirement"], [["BR-001", "one"], ["BR-002", "accepts a spec and the"]])
    page2 = DocTable(["ID", "Requirement"], [["", "RuleBook XML as inputs"], ["BR-003", "three"]])
    out = merge_continued([page1, page2])
    assert len(out) == 1
    assert [r[0] for r in out[0].rows] == ["BR-001", "BR-002", "BR-003"]
    assert out[0].rows[1][1] == "accepts a spec and the RuleBook XML as inputs"


# ---- "In scope | Out of scope": two lists, never pairs ----------------------

def test_in_and_out_of_scope_columns_become_two_tagged_lists():
    from aryx.connectors.doc_tables import DocTable, split_scope_table
    t = DocTable(["In scope", "Out of scope"], [
        ["Sandbox first, then production", "Oracle Fusion CPQ"],
        ["Human Gate 1 and Gate 2", "Editing quotes or orders"],
        ["Snapshot, verification, rollback", ""],          # shorter list: no pairing
    ])
    out = split_scope_table(t)
    assert out.header == ["name", "scope"]
    assert [r for r in out.rows if r[1] == "in scope"] == [
        ["Sandbox first, then production", "in scope"],
        ["Human Gate 1 and Gate 2", "in scope"],
        ["Snapshot, verification, rollback", "in scope"]]
    assert [r[0] for r in out.rows if r[1] == "out of scope"] == [
        "Oracle Fusion CPQ", "Editing quotes or orders"]
    # nothing carries the other column's text
    assert not any("Oracle" in r[0] and r[1] == "in scope" for r in out.rows)


def test_other_two_column_tables_are_not_scope_tables():
    from aryx.connectors.doc_tables import DocTable, split_scope_table
    assert split_scope_table(DocTable(["Term", "Meaning"], [["a", "b"]])) is None
    assert split_scope_table(DocTable(["In scope", "Notes"], [["a", "b"]])) is None


def test_plural_headings_that_name_the_type_are_dropped_but_real_items_stay():
    from aryx.connectors.doc_tables import is_redundant_mention
    for name, kind in [("Performance reviews", "PerformanceReview"),
                       ("Business requirements", "Requirement"),
                       ("employees", "Employee"), ("Departments", "Department"),
                       ("Risks", "Risk"), ("Policies", "Policy")]:
        assert is_redundant_mention(name, kind, {}), (name, kind)
    for name, kind in [("Login requirement", "Requirement"),      # singular: a real item
                       ("Northwind Radio Systems", "Organization"),
                       ("Senior", "Role"), ("miscalibrated score", "Risk")]:
        assert not is_redundant_mention(name, kind, {}), (name, kind)


# ---- tables without ruled lines ---------------------------------------------

def _borderless_pdf(tmp_path, rows, header=("Emp ID", "Name", "Dept ID", "Role")):
    """A PDF whose table is only aligned text: no lines at all."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    xs = [60, 140, 300, 380]
    page.insert_text((60, 60), "Staff list", fontsize=14)
    for r, row in enumerate([list(header)] + rows):
        for x, cell in zip(xs, row):
            page.insert_text((x, 100 + r * 22), cell, fontsize=10)
    path = tmp_path / "borderless.pdf"
    doc.save(str(path))
    return path


_BORDERLESS_ROWS = [["E001", "Arjun Mehta", "D1", "Manager"], ["E002", "Priya Nair", "D1", "Engineer"],
                    ["E003", "Rahul Iyer", "D2", "Support"], ["E004", "Kavya Reddy", "D2", "Analyst"],
                    ["E005", "Sana Khan", "D3", "Sales"]]


def test_a_table_drawn_without_lines_is_still_read_as_rows(tmp_path):
    from aryx.connectors.doc_tables import extract_tables
    path = _borderless_pdf(tmp_path, _BORDERLESS_ROWS)
    tables = extract_tables(path.read_bytes(), ".pdf")
    assert len(tables) == 1
    assert tables[0].header == ["Emp ID", "Name", "Dept ID", "Role"]
    assert len(tables[0].rows) == 5 and tables[0].rows[0][1] == "Arjun Mehta"


def test_ordinary_paragraphs_are_never_read_as_a_table(tmp_path):
    import fitz
    from aryx.connectors.doc_tables import extract_tables
    doc = fitz.open()
    page = doc.new_page()
    text = ("The bot applies approved configuration changes through the admin screen. "
            "A human approves every plan before anything is touched, and every step is "
            "verified afterwards. If a step cannot be verified it is treated as below the "
            "confidence threshold and a person decides.\n\n"
            "Interruptions are expected: the bot resumes from the last committed step and "
            "never repeats work that already succeeded. Everything is recorded for audit.")
    page.insert_textbox(fitz.Rect(60, 60, 540, 400), text, fontsize=10)
    path = tmp_path / "prose.pdf"
    doc.save(str(path))
    assert extract_tables(path.read_bytes(), ".pdf") == []


def test_the_borderless_check_rejects_data_that_does_not_look_like_a_table():
    from aryx.connectors.doc_tables import DocTable, looks_like_a_table
    good = DocTable(["A", "B", "C"], [["1", "x", "y"], ["2", "x", "y"], ["3", "x", "y"]])
    assert looks_like_a_table(good)
    assert not looks_like_a_table(DocTable(["A", "B"], good.rows))                # 2 columns
    assert not looks_like_a_table(DocTable(["A", "B", "C"], good.rows[:2]))       # 2 rows
    assert not looks_like_a_table(DocTable(["A", "", "C"], good.rows))            # unnamed column
    long_cells = [["a long sentence " * 6, "b", "c"]] * 3
    assert not looks_like_a_table(DocTable(["A", "B", "C"], long_cells))          # prose-length cells
    sparse = [["1", "", ""], ["2", "", ""], ["3", "x", "y"]]
    assert not looks_like_a_table(DocTable(["A", "B", "C"], sparse))              # mostly empty


# ---- tables name their own rows; paragraphs do not restate a table's list ----

def test_a_document_table_with_an_id_column_is_typed_from_its_header_without_the_model(monkeypatch):
    from aryx.pipeline import doc_discovery as dd

    def _must_not_ask(*_a, **_k):
        raise AssertionError("the model must not be asked for a table that names itself")

    monkeypatch.setattr(dd.llm_runtime, "chat", _must_not_ask)
    plan = dd._infer_type("ID,Rule\nBRU-001,No write without approval\n", "BRD_table5.csv", "",
                          prefer_header=True)
    assert plan == {"ontology_type": "Rule", "match_keys": ["ID", "Rule"]}
    plan = dd._infer_type("ID,Priority,Requirement,Acceptance criteria\nBR-001,Must,x,y\n",
                          "BRD_table4.csv", "", prefer_header=True)
    assert plan["ontology_type"] == "Requirement"


def test_header_typing_is_only_for_document_tables_and_only_with_an_id_column(monkeypatch):
    from aryx.pipeline import doc_discovery as dd
    asked = []
    monkeypatch.setattr(dd.llm_runtime, "chat", lambda *a, **k: (
        asked.append(1) or ('{"ontology_type":"Customer","match_keys":["Email"]}', 1, 1)))
    # a normal uploaded CSV keeps the old behaviour (the model decides)
    assert dd._infer_type("ID,Rule\nB1,x\n", "rules.csv", "")["ontology_type"] == "Customer"
    # a document table without an id column is still left to the model
    assert dd._infer_type("Term,Meaning\nA,b\n", "t.csv", "", prefer_header=True)[
        "ontology_type"] == "Customer"
    assert len(asked) == 2


def test_paragraph_mentions_of_a_kind_a_table_already_lists_are_dropped():
    from aryx.connectors.doc_tables import is_redundant_mention
    covered = {"requirement": {"the bot applies approved changes"}, "metric": {"rollback rate"},
               "risk": set(), "rule": set()}
    # restated principle, a heading, a stray item: none is an extra requirement/metric/risk
    assert is_redundant_mention("Make every change reversible", "Requirement", covered)
    assert is_redundant_mention("Success measures", "Metric", covered)
    assert is_redundant_mention("miscalibrated score", "Risk", covered)
    assert is_redundant_mention("Keep a human in control: approve plans", "BusinessRequirement",
                                covered)                                       # qualified type
    # a proper name or an id is information, even for a kind a table lists
    assert not is_redundant_mention("Visiting Auditor", "Requirement", covered)
    assert not is_redundant_mention("CTRL-010", "Requirement", covered)
    # kinds no table covers are kept, and short types never match by accident
    assert not is_redundant_mention("Northwind Radio Systems", "Organization", covered)
    assert not is_redundant_mention("Q4", "Date", covered)
    assert not is_redundant_mention("anything", "Requirement", {})            # no tables, nothing dropped


def test_a_bare_value_is_not_a_name_but_ids_and_proper_names_are():
    from aryx.connectors.doc_tables import _looks_like_a_name, is_redundant_mention
    for value in ("95%", "2025", "30 days", "3.5"):
        assert not _looks_like_a_name(value), value
    for name in ("Visiting Auditor", "CTRL-010", "Q4 Review", "Oracle CPQ"):
        assert _looks_like_a_name(name), name
    covered = {"metric": set()}
    assert is_redundant_mention("95%", "Metric", covered)            # the stray BRD "metric"
    assert not is_redundant_mention("Oracle CPQ", "Metric", covered)


def test_the_header_fallback_gives_clean_type_names():
    from aryx.pipeline.doc_discovery import _header_type
    assert _header_type("Today (as-is),Consequence\n")["ontology_type"] == "Today"
    assert _header_type("Who,Role in this project\n")["ontology_type"] == "RoleProject"
    assert _header_type("ID,Decisions,Status\n")["ontology_type"] == "Decision"
    assert _header_type("Term,Meaning\n") is None
