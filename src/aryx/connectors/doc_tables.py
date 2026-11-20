"""Real tables inside PDF / DOCX files, read as rows instead of plain text.

Plain-text extraction flattens a table, so an LLM reading it keeps a handful of
"interesting" cells and loses most rows. Here every table becomes a header plus
rows, which the file-ingest job then lands exactly like an uploaded CSV (one
record per row, type + keys inferred from the header, foreign keys linked).

* PDF  — PyMuPDF ``Page.find_tables`` (ruled tables; no extra dependency).
* DOCX — python-docx ``Document.tables`` (the text extractor skips them, so
  before this their content was dropped entirely).

A table that continues on the next page repeats its header row; tables with an
identical header are merged into one.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx"}
TABLE_SUFFIXES = PDF_SUFFIXES | DOCX_SUFFIXES


@dataclass
class DocTable:
    """One table: a header row and its data rows (all cells are strings)."""

    header: list[str]
    rows: list[list[str]] = field(default_factory=list)

    def to_csv(self) -> bytes:
        """Serialise as UTF-8 CSV so the normal CSV ingest path can read it."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(self.header)
        writer.writerows(self.rows)
        return buf.getvalue().encode("utf-8")


_HYPHEN_BREAK = re.compile(r"-[ \t]*\r?\n[ \t]*")


def _clean(cell: object) -> str:
    """One cell as single-line text ("Manager<newline>ID" -> "Manager ID").

    A line break right after a hyphen is a wrap inside one word or id
    ("STG-<newline>PREP" -> "STG-PREP"), so it is joined without a space;
    otherwise the id would never match its other uses in the document.
    """
    return " ".join(_HYPHEN_BREAK.sub("-", str(cell or "")).split())


def _unique_header(cells: list[str]) -> list[str]:
    """Blank / repeated header names get a suffix so no column is overwritten."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for i, cell in enumerate(cells, start=1):
        name = cell or f"column_{i}"
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return out


def _to_table(raw: list[list[object]]) -> DocTable | None:
    """Raw cell grid -> DocTable, or None when it is not a usable table.

    Usable = a header row with at least two named columns and one data row.
    """
    grid = [[_clean(c) for c in row] for row in raw]
    grid = [row for row in grid if any(row)]
    if len(grid) < 2:
        return None
    width = max(len(row) for row in grid)
    grid = [row + [""] * (width - len(row)) for row in grid]
    keep = [i for i in range(width) if any(row[i] for row in grid)]
    grid = [[row[i] for i in keep] for row in grid]
    if sum(1 for c in grid[0] if c) < 2:
        return None
    return DocTable(header=_unique_header(grid[0]), rows=_join_wrapped_rows(grid[1:]))


def _is_continuation(row: list[str]) -> bool:
    """An empty first cell AND at most half the cells filled: the second line of a row.

    A real record that merely lacks an id has most of its cells filled and stays a
    row of its own.
    """
    filled = sum(1 for c in row if c.strip())
    return not row[0].strip() and filled * 2 <= len(row)


def _join_wrapped_rows(rows: list[list[str]]) -> list[list[str]]:
    """Join a row that wrapped onto a second line back into the row above it.

    In a table whose first column is an identifier (BR-001, RISK-006 ...), a
    row with an EMPTY first cell is the second line of the previous row, not a
    new record. Only done when the first column is filled in nearly every row,
    so a table that leaves that column blank on purpose is untouched.
    """
    if len(rows) < 3:
        return rows
    filled = sum(1 for r in rows if r[0].strip())
    if filled / len(rows) < 0.8:
        return rows
    out: list[list[str]] = []
    for row in rows:
        if out and _is_continuation(row):
            prev = out[-1]
            out[-1] = [(a + " " + b).strip() if b else a for a, b in zip(prev, row)]
        else:
            out.append(list(row))
    return out


def merge_continued(tables: list[DocTable],
                    pages: list[int] | None = None) -> list[DocTable]:
    """Join a table to the one just before it when they share a header.

    That is a table split across a page break. With ``pages`` (the page of each table)
    the two must also be on consecutive pages, so two different tables that merely
    start with the same header ("ID | Description") in different sections stay apart.
    """
    out: list[DocTable] = []
    last_key: tuple[str, ...] | None = None
    last_page: int | None = None
    for index, table in enumerate(tables):
        key = tuple(h.lower() for h in table.header)
        page = pages[index] if pages is not None else None
        continues = (out and key == last_key and (
            page is None or last_page is None or page == last_page + 1))
        last_key, last_page = key, page
        if continues:
            target = out[-1]
            rows = [list(r) for r in table.rows]
            # A row that broke across the page: the next page repeats the header
            # and then finishes the row with an empty first cell.
            first = rows[0] if rows else None
            if (first is not None and _is_continuation(first) and target.rows
                    and all(r[0].strip() for r in rows[1:])):
                prev = target.rows[-1]
                target.rows[-1] = [(a + " " + b).strip() if b else a
                                   for a, b in zip(prev, first)]
                rows = rows[1:]
            target.rows.extend(rows)
        else:
            out.append(DocTable(list(table.header), list(table.rows)))
    return out


def looks_like_a_table(table: DocTable) -> bool:
    """Strict check for a table found WITHOUT ruled lines.

    Aligned paragraph text can be mistaken for a borderless table, so a
    candidate must look like data: at least 3 columns and 3 rows, a short fully
    named header, short cells, and rows that are mostly filled in.
    """
    cols = len(table.header)
    if cols < 3 or cols > 12 or len(table.rows) < 3:
        return False
    if not all(h.strip() for h in table.header) or max(len(h) for h in table.header) > 40:
        return False
    for col in range(cols):                       # a prose-like column is not data
        texts = [row[col] for row in table.rows if row[col].strip()]
        if texts and sum(len(t) for t in texts) / len(texts) > 60:
            return False
    full_rows = sum(1 for row in table.rows if sum(1 for c in row if c.strip()) >= cols - 1)
    return full_rows / len(table.rows) >= 0.8


def _drop_caption_rows(raw: list[list[object]]) -> list[list[object]]:
    """Drop leading rows with a single filled cell (a caption such as "Staff list").

    Text-aligned detection draws its box around the caption too; the real header
    is the first row that has several filled cells.
    """
    rows = [r for r in raw if any(str(c or "").strip() for c in r)]
    while len(rows) > 1 and sum(1 for c in rows[0] if str(c or "").strip()) <= 1:
        rows = rows[1:]
    return rows


def _tables_from(found, check=None) -> list[tuple[tuple[float, ...], DocTable]]:
    out = []
    for item in found:
        raw = item.extract()
        table = _to_table(_drop_caption_rows(raw) if check is not None else raw)
        if table is not None and (check is None or check(table)):
            out.append((tuple(item.bbox), table))
    return out


def pdf_page_tables(page) -> list[tuple[tuple[float, ...], DocTable]]:
    """(bounding box, table) for each usable table on a PyMuPDF page.

    Ruled tables first. A page with none is tried once more WITHOUT ruled lines
    (columns found from the text alignment), and only a candidate that
    ``looks_like_a_table`` is accepted, so ordinary prose is never read as one.
    """
    try:
        found = page.find_tables().tables
    except Exception as exc:  # noqa: BLE001 - table detection is best-effort
        logger.debug("find_tables failed: %s", exc)
        return []
    out = _tables_from(found)
    if out:
        return out
    try:
        return _tables_from(page.find_tables(strategy="text").tables, looks_like_a_table)
    except Exception as exc:  # noqa: BLE001
        logger.debug("find_tables(text) failed: %s", exc)
        return []


def extract_tables(data: bytes, suffix: str, ocr=None) -> list[DocTable]:
    """All usable tables in a PDF or DOCX upload ([] for anything else).

    ``ocr`` (a PageOcr) lets a scanned PDF page contribute the tables it shows.
    """
    suffix = suffix.lower()
    pages: list[int] | None = None
    try:
        if suffix in PDF_SUFFIXES:
            tables, pages = _pdf_tables(data, ocr)
        elif suffix in DOCX_SUFFIXES:
            tables = _docx_tables(data)
        else:
            return []
    except Exception as exc:  # noqa: BLE001 — never fail the upload over tables
        logger.warning("table extraction skipped (%s): %s", suffix, exc)
        return []
    return merge_continued(tables, pages)


def _pdf_tables(data: bytes, ocr=None) -> tuple[list[DocTable], list[int]]:
    """(tables in reading order, the page each one is on)."""
    import fitz  # pymupdf

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if ocr is None:
            pairs = [(n, t) for n, page in enumerate(doc, start=1) for _, t in pdf_page_tables(page)]
            return [t for _, t in pairs], [n for n, _ in pairs]
        from aryx.connectors.ocr_vision import doc_key, page_is_blank, split_markdown_tables

        key = doc_key(data)
        tables: list[DocTable] = []
        where: list[int] = []
        for number, page in enumerate(doc, start=1):
            found = [t for _, t in pdf_page_tables(page)]
            if not found and page_is_blank(page):      # a scan: read the picture
                found = split_markdown_tables(ocr.text(key, number, page))[1]
            tables.extend(found)
            where.extend([number] * len(found))
        return tables, where
    finally:
        doc.close()


def _docx_tables(data: bytes) -> list[DocTable]:
    import docx

    document = docx.Document(io.BytesIO(data))
    tables = (_to_table([[c.text for c in row.cells] for row in t.rows])
              for t in document.tables)
    return [t for t in tables if t is not None]


# A catalogue table lists many kinds of thing in one table, with a column that
# says which kind ("id | type | name": ACT-ADM | Actor | CPQ Administrator).
# Its file name carries the kind after this separator so the landing code can
# type each row by its own value instead of one type for the whole table.
TYPE_SEP = "__as__"


def pin_from_name(file_name: str) -> str | None:
    """The row type a split catalogue file carries in its name, else None."""
    stem = Path(file_name).stem
    return stem.split(TYPE_SEP, 1)[1] if TYPE_SEP in stem else None


def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _catalogue_columns(table: DocTable) -> tuple[int, int] | None:
    """(id column, type column) when the table is an id / type / name catalogue."""
    names = [_norm(h) for h in table.header]
    if not ({"id", "type", "name"} <= set(names)):
        return None
    if any(names.count(n) != 1 for n in ("id", "type", "name")):
        return None
    return names.index("id"), names.index("type")


def _kind(value: str) -> str:
    """A type value as a safe ontology type name ("Business Rule" -> BusinessRule)."""
    text = value.title() if " " in value else value
    return "".join(ch for ch in text if ch.isalnum())


def split_catalogue(
    table: DocTable, known_ids: set[str],
) -> list[tuple[str, DocTable]] | None:
    """Split an id / type / name catalogue into one table per ``type`` value.

    Rows whose id is already a row of another table are dropped: that table holds
    the full record, so a second entity from this list would only duplicate it.
    What stays are the things the document names only here (Actors, Stages ...).
    Returns None when the table is not a catalogue (or has a single kind).
    """
    cols = _catalogue_columns(table)
    if cols is None:
        return None
    id_i, type_i = cols
    groups: dict[str, list[list[str]]] = {}
    for row in table.rows:
        kind = _kind(row[type_i].strip()) or "Item"   # a row with no kind still lands
        groups.setdefault(kind, []).append(row)
    if len(groups) < 2:
        return None
    out = []
    for kind, rows in groups.items():
        fresh = [r for r in rows if r[id_i].strip().lower() not in known_ids]
        if fresh:
            out.append((kind, DocTable(list(table.header), fresh)))
    return out


def split_scope_table(table: DocTable) -> DocTable | None:
    """Read an "In scope | Out of scope" table as two lists, not as pairs.

    The two columns are independent lists that happen to sit side by side;
    reading each row as one record glues an out-of-scope item onto an unrelated
    in-scope one. Every non-empty cell becomes its own row, tagged with the list
    it came from (``name | scope``). None when the table is not of that shape.
    """
    names = [_norm(h) for h in table.header]
    if "inscope" not in names or "outofscope" not in names:
        return None
    cols = {"in scope": names.index("inscope"), "out of scope": names.index("outofscope")}
    rows = [[row[i].strip(), scope] for scope, i in cols.items()
            for row in table.rows if row[i].strip()]
    return DocTable(["name", "scope"], rows) if rows else None


def tables_as_csv_files(
    items: list[tuple[bytes, str]], ocr=None,
) -> tuple[list[tuple[bytes, str]], set[str]]:
    """Turn the tables of uploaded PDF/DOCX files into CSV uploads.

    Returns ``(csv_files, names_with_tables)``: ``csv_files`` are
    ``(bytes, "<stem>_table<N>.csv")`` pairs for the normal CSV path, and
    ``names_with_tables`` are the source files that yielded at least one table.
    An id / type / name catalogue becomes one file per kind
    (``<stem>_table<N>__as__<Kind>.csv``, see :func:`pin_from_name`).
    """
    csv_files: list[tuple[bytes, str]] = []
    with_tables: set[str] = set()
    for data, name in items:
        tables = extract_tables(data, Path(name).suffix, ocr)
        stem = Path(name).stem
        # ids that other tables already hold in full (not the catalogue itself)
        from aryx.pipeline.relation_rows import relation_columns  # noqa: PLC0415
        known_ids: set[str] = set()
        for table in tables:
            # a from/predicate/to table only *mentions* ids; it holds no records
            if _catalogue_columns(table) is None and relation_columns(table.header) is None:
                known_ids.update(c.strip().lower() for row in table.rows for c in row
                                 if 2 <= len(c.strip()) <= 40)
        for number, table in enumerate(tables, start=1):
            scope = split_scope_table(table)
            if scope is not None:
                csv_files.append((scope.to_csv(),
                                  f"{stem}_table{number}{TYPE_SEP}ScopeItem.csv"))
                logger.info("scope table %d of %s: %d item(s) as one list", number, name,
                            len(scope.rows))
                continue
            parts = split_catalogue(table, known_ids)
            if parts is None:
                csv_files.append((table.to_csv(), f"{stem}_table{number}.csv"))
                logger.info("table %d of %s: %d rows x %d cols", number, name,
                            len(table.rows), len(table.header))
                continue
            for kind, part in parts:
                csv_files.append((part.to_csv(),
                                  f"{stem}_table{number}{TYPE_SEP}{kind}.csv"))
                logger.info("catalogue table %d of %s: %d new %s row(s)",
                            number, name, len(part.rows), kind)
        if tables:
            with_tables.add(name)
    return csv_files, with_tables


def table_values(csv_bytes: bytes) -> set[str]:
    """Every cell value of a table CSV, lower-cased (3+ chars), for matching."""
    values: set[str] = set()
    for row in csv.reader(io.StringIO(csv_bytes.decode("utf-8"))):
        values.update(" ".join(c.split()).lower() for c in row if len(c.strip()) >= 3)
    return values


# Types the LLM gives to headings, titles and captions of a document. When the
# document's tables already hold the real data, these are page furniture
# ("Employees", "Performance reviews (2025)", "HR notes", the file title), not
# entities.
STRUCTURAL_TYPES = frozenset({
    "category", "dataset", "section", "heading", "title", "table", "list",
    "document", "report", "file", "sheet", "chapter", "topic", "label",
})


def _alnum(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _looks_like_a_name(name: str) -> bool:
    """True for a proper name or an identifier ("Visiting Auditor", "CTRL-010").

    A restated requirement, risk or heading reads as a phrase with lower-case
    words ("Make every change reversible", "Success measures"); a person, team or
    organisation is written with capital letters throughout and stays.
    """
    words = re.findall(r"[A-Za-z0-9][\w'-]*", name)
    if not 0 < len(words) <= 4 or not all(w[0].isupper() or w[0].isdigit() for w in words):
        return False
    return any(w[0].isupper() for w in words)      # "95%" or "2025" alone is a value, not a name


def _type_held_by_a_table(kind: str, covered: dict[str, set[str]]) -> bool:
    """True when an ingested table already is the list of this kind of thing.

    A document with a Requirements table states its requirements there; the
    paragraphs around it restate or summarise them, and counting both made the
    answer to "how many requirements?" twice as big. Matching ignores case and a
    leading qualifier (Requirement / BusinessRequirement), and needs 4+
    characters to match. Only phrase-like mentions are dropped on this ground
    (see ``_looks_like_a_name``).
    """
    k = _alnum(kind)
    for held in covered:
        h = _alnum(held)
        if min(len(k), len(h)) >= 4 and (k == h or k.endswith(h) or h.endswith(k)):
            return True
    return False


def _names_the_type_in_plural(name: str, kind: str) -> bool:
    """True for a heading-like name that is just the type, or its plural.

    "employees" for Employee, "Performance reviews" for PerformanceReview and
    "Business requirements" for Requirement are section headings the model read
    as entities. Spaces and case are ignored, and a leading qualifier is fine
    ("Business requirements"), but only a PLURAL ending counts: "Login
    requirement" is a real item and stays.
    """
    n, k = _alnum(name), _alnum(kind)
    if not k:
        return False
    plurals = {k, k + "s", k + "es"}
    if k.endswith("y"):
        plurals.add(k[:-1] + "ies")
    return n in plurals or any(n.endswith(p) for p in plurals - {k})


def is_redundant_mention(name: str, mention_type: str,
                         covered: dict[str, set[str]]) -> bool:
    """True for a text mention that adds nothing next to the ingested tables.

    * a PII placeholder such as ``<PERSON>`` (never a real entity);
    * the bare type label itself ("employees", "Departments" for an Employee /
      Department mention), typically picked up from a heading or a sentence;
    * a heading / title / caption (type Category, Dataset, Section, ...);
    * a name already present in a table of the same type — the table row is the
      entity, so a second one from the prose would only duplicate it.
    """
    n = " ".join(name.split()).lower()
    if not n:
        return False
    if n.startswith("<") and n.endswith(">"):
        return True
    kind = mention_type.strip().lower()
    if kind in STRUCTURAL_TYPES:
        return True
    if _type_held_by_a_table(kind, covered) and not _looks_like_a_name(name):
        return True
    if kind and _names_the_type_in_plural(n, kind):
        return True
    return n in covered.get(kind, ())
