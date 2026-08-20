"""Shape-mismatch guard for the raw multi-file ingest endpoint.

Root cause (workspace 39 incident): the endpoint accepts ONE ontology_type
for the whole batch. Upload 3 differently-shaped CSVs (companies, tickets,
customers) with an explicit type and every row lands under that one type,
regardless of its actual columns. The default path (empty/'Document') is
fine — it already infers a type per file. The bug only bites when a caller
pins an explicit shared type across files that don't actually share a shape.

Fix: a cheap, deterministic column-set diff — no LLM — that detects that
exact situation and falls back to per-file auto-detection (the same
inference the empty/'Document' path already uses) instead of forcing the
caller's one type onto every file. `file_types`, an optional
{filename: ontology_type} map, remains available for callers who want
explicit per-file control instead of auto-detection.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from aryx.api.file_ingest_api import (
    _columns,
    _parse_file_types,
    _resolve_batch_ontology_type,
    _shape_mismatches,
)

_TICKETS_CSV = b"TicketID,Issue,CustomerID\nT101,Radio not booting,1\nT102,Firmware crash,2\n"
_CUSTOMERS_CSV = b"CustomerID,Name,Company\n1,John Smith,Acme\n2,David Chen,Globex\n"
_CUSTOMERS_CSV_SPARSE = b"CustomerID,Name,Company,Notes\n1,John Smith,Acme,\n2,David Chen,Globex,VIP\n"


def test_columns_reads_csv_header() -> None:
    assert _columns(_TICKETS_CSV, ".csv") == {"TicketID", "Issue", "CustomerID"}


def test_columns_reads_json_first_row_flattened() -> None:
    data = json.dumps([{"a": 1, "b": {"c": 2}}]).encode()
    assert _columns(data, ".json") == {"a", "b.c"}


def test_columns_empty_on_unparseable_json() -> None:
    assert _columns(b"not json at all {", ".json") == set()


def test_shape_mismatches_detects_divergent_csv_columns() -> None:
    items = [(_TICKETS_CSV, "tickets.csv"), (_CUSTOMERS_CSV, "customers.csv")]
    mismatched = _shape_mismatches(items, file_types={})
    assert set(mismatched) == {"tickets.csv", "customers.csv"}


def test_shape_mismatches_empty_when_columns_overlap_enough() -> None:
    same_shape = [
        (_CUSTOMERS_CSV, "customers1.csv"),
        (_CUSTOMERS_CSV_SPARSE, "customers2.csv"),
    ]
    assert _shape_mismatches(same_shape, file_types={}) == []


def test_shape_mismatches_skips_files_covered_by_file_types_map() -> None:
    items = [(_TICKETS_CSV, "tickets.csv"), (_CUSTOMERS_CSV, "customers.csv")]
    # Both filed individually — nothing left to compare, so no mismatch.
    mismatched = _shape_mismatches(
        items, file_types={"tickets.csv": "Ticket", "customers.csv": "Customer"})
    assert mismatched == []


def test_shape_mismatches_ignores_single_file() -> None:
    assert _shape_mismatches([(_TICKETS_CSV, "tickets.csv")], file_types={}) == []


def test_resolve_batch_ontology_type_falls_back_to_auto_detect_on_mismatch() -> None:
    """The workspace-39 scenario: one explicit type, 3 differently-shaped
    files. Must NOT force 'Customer' onto everything — must hand back "" so
    the per-file inference cascade in _run_files classifies each file."""
    items = [(_TICKETS_CSV, "tickets.csv"), (_CUSTOMERS_CSV, "customers.csv")]
    assert _resolve_batch_ontology_type(items, "Customer", file_types={}) == ""


def test_resolve_batch_ontology_type_passes_through_document_unchanged() -> None:
    items = [(_TICKETS_CSV, "tickets.csv"), (_CUSTOMERS_CSV, "customers.csv")]
    assert _resolve_batch_ontology_type(items, "Document", file_types={}) == "Document"


def test_resolve_batch_ontology_type_passes_through_empty_unchanged() -> None:
    items = [(_TICKETS_CSV, "tickets.csv"), (_CUSTOMERS_CSV, "customers.csv")]
    assert _resolve_batch_ontology_type(items, "", file_types={}) == ""


def test_resolve_batch_ontology_type_keeps_shared_type_when_file_types_covers_all() -> None:
    items = [(_TICKETS_CSV, "tickets.csv"), (_CUSTOMERS_CSV, "customers.csv")]
    resolved = _resolve_batch_ontology_type(
        items, "Customer",
        file_types={"tickets.csv": "Ticket", "customers.csv": "Customer"})
    assert resolved == "Customer"


def test_resolve_batch_ontology_type_keeps_shared_type_for_same_shape_files() -> None:
    items = [(_CUSTOMERS_CSV, "batch1.csv"), (_CUSTOMERS_CSV_SPARSE, "batch2.csv")]
    assert _resolve_batch_ontology_type(items, "Customer", file_types={}) == "Customer"


def test_parse_file_types_returns_empty_dict_for_blank_input() -> None:
    assert _parse_file_types("") == {}
    assert _parse_file_types("   ") == {}


def test_parse_file_types_parses_valid_json() -> None:
    assert _parse_file_types('{"tickets.csv": "Ticket"}') == {"tickets.csv": "Ticket"}


def test_parse_file_types_rejects_malformed_json() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _parse_file_types("{not json")
    assert exc_info.value.status_code == 400


def test_parse_file_types_rejects_non_object_json() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _parse_file_types('["tickets.csv", "Ticket"]')
    assert exc_info.value.status_code == 400


def test_parse_file_types_rejects_non_string_values() -> None:
    """A wrong type here must fail loudly at upload time, not silently flow
    into the ingest pipeline and surface as a confusing background-job
    failure much later."""
    with pytest.raises(HTTPException) as exc_info:
        _parse_file_types('{"tickets.csv": 123}')
    assert exc_info.value.status_code == 400
