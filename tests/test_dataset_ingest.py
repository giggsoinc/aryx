"""Tests for Dataset Upload & Ingestion (C02) — pure, no DB.

Uses an in-memory fake sink so register_dataset's validation, hashing,
enumeration, dedupe, and versioning are exercised without Postgres.
"""
from __future__ import annotations

from aryx.dataset.formats import detect, enumerate_data
from aryx.dataset.ingest import register_dataset
from aryx.dataset.models import DatasetIngestResult

CSV = b"id,name,region\n1,Acme,west\n2,Globex,east\n3,Initech,west\n"
JSON = b'[{"id": 1, "region": "west"}, {"id": 2, "region": "east"}]'


class _FakeSink:
    """Minimal in-memory DatasetSink for register_dataset."""

    def __init__(self) -> None:
        self.by_hash: dict[tuple[str, str], DatasetIngestResult] = {}
        self.counts: dict[str, int] = {}
        self.saved: list[DatasetIngestResult] = []

    def find_version_by_hash(self, dataset_id, content_hash):
        return self.by_hash.get((dataset_id, content_hash))

    def count_versions(self, dataset_id):
        return self.counts.get(dataset_id, 0)

    def upsert_dataset(self, dataset_id, request_id, file_name):
        self.counts.setdefault(dataset_id, 0)

    def save_version(self, result, raw_bytes):
        self.counts[result.dataset_id] = self.counts.get(result.dataset_id, 0) + 1
        self.by_hash[(result.dataset_id, result.content_hash)] = result
        self.saved.append(result)


def _ingest(data: bytes, name: str, sink: _FakeSink, request_id: str = "req_1"):
    return register_dataset(data=data, file_name=name, request_id=request_id, store=sink)


def test_detect_csv_and_json() -> None:
    assert detect(CSV, ".csv") == ("csv", None)
    assert detect(JSON, ".json") == ("json", None)


def test_detect_rejects_encrypted_ole() -> None:
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest"
    fmt, reason = detect(ole, ".xls")
    assert reason and "encrypted" in reason


def test_detect_rejects_xlsx_zip() -> None:
    fmt, reason = detect(b"PK\x03\x04zipbody", ".xlsx")
    assert reason and "xlsx" in reason.lower()


def test_enumerate_csv() -> None:
    cols, rows = enumerate_data(CSV, "csv")
    assert cols == ["id", "name", "region"]
    assert rows == 3


def test_enumerate_json() -> None:
    cols, rows = enumerate_data(JSON, "json")
    assert "id" in cols and "region" in cols
    assert rows == 2


def test_accepts_and_versions() -> None:
    sink = _FakeSink()
    res = _ingest(CSV, "contracts_1000.csv", sink)
    assert res.ingestion_status == "accepted"
    assert res.dataset_id == "dataset_contracts_1000"
    assert res.dataset_version == "v1"
    assert res.format == "csv"
    assert res.content_hash.startswith("sha256:")
    assert res.raw_snapshot_ref == "raw/dataset_contracts_1000/v1"
    assert res.row_count_estimate == 3
    assert len(sink.saved) == 1


def test_identical_content_is_duplicate_not_new_version() -> None:
    sink = _FakeSink()
    _ingest(CSV, "contracts.csv", sink)
    again = _ingest(CSV, "contracts.csv", sink)
    assert again.ingestion_status == "duplicate"
    assert again.dataset_version == "v1"
    assert len(sink.saved) == 1  # no second snapshot


def test_changed_content_becomes_next_version() -> None:
    sink = _FakeSink()
    _ingest(CSV, "contracts.csv", sink)
    changed = _ingest(CSV + b"4,Umbrella,north\n", "contracts.csv", sink)
    assert changed.ingestion_status == "accepted"
    assert changed.dataset_version == "v2"
    assert len(sink.saved) == 2


def test_rejected_content_is_not_persisted() -> None:
    sink = _FakeSink()
    res = _ingest(b"PK\x03\x04xlsxbody", "book.xlsx", sink)
    assert res.ingestion_status == "rejected"
    assert res.errors
    assert len(sink.saved) == 0


def test_invalid_json_rejected() -> None:
    sink = _FakeSink()
    res = _ingest(b"{not valid json", "bad.json", sink)
    assert res.ingestion_status == "rejected"
    assert any("json" in e.lower() for e in res.errors)


def test_utf8_bom_csv_accepted_and_first_header_clean() -> None:
    bom = b"\xef\xbb\xbf" + b"id,name\n1,Acme\n2,Globex\n"
    cols, rows = enumerate_data(bom, "csv")
    assert cols == ["id", "name"]              # BOM stripped, not '﻿id'
    assert rows == 2
    fmt, reason = detect(bom, ".csv")
    assert reason is None and fmt == "csv"


def test_utf8_bom_json_accepted() -> None:
    bom = b"\xef\xbb\xbf" + b'[{"id": 1}, {"id": 2}]'
    fmt, reason = detect(bom, ".json")
    assert reason is None and fmt == "json"
    cols, rows = enumerate_data(bom, "json")
    assert "id" in cols and rows == 2


def test_duplicate_csv_headers_deduped() -> None:
    cols, _ = enumerate_data(b"id,id,name\n1,2,x\n", "csv")
    assert cols == ["id", "id_2", "name"]


def test_version_collision_retries_then_bumps() -> None:
    from psycopg.errors import UniqueViolation

    class _RaceSink(_FakeSink):
        def __init__(self) -> None:
            super().__init__()
            self.raised = False

        def save_version(self, result, raw_bytes):
            if not self.raised:               # simulate a concurrent v1 winner
                self.raised = True
                self.counts[result.dataset_id] = 1   # someone else took v1
                raise UniqueViolation("duplicate key")
            super().save_version(result, raw_bytes)

    sink = _RaceSink()
    res = _ingest(CSV, "contracts.csv", sink)
    assert res.ingestion_status == "accepted"
    assert res.dataset_version == "v2"        # retried past the taken v1
    assert len(sink.saved) == 1
