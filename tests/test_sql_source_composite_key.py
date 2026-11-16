"""SqlConnector must keep rows distinct when the primary key is composite.

Regression: only the first key column became the record id, so every line
of one purchase order (po_number + line_number) shared the same id.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from aryx.connectors.sql_source import SqlConnector


@pytest.fixture
def sqlite_url():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    url = f"sqlite:///{path}"
    engine = create_engine(url)
    meta = MetaData()
    lines = Table(
        "supply_chain", meta,
        Column("po_number", String, primary_key=True),
        Column("line_number", Integer, primary_key=True),
        Column("item_sku", String),
    )
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(lines.insert(), [
            {"po_number": "PO1", "line_number": 1, "item_sku": "A"},
            {"po_number": "PO1", "line_number": 2, "item_sku": "B"},
            {"po_number": "PO2", "line_number": 1, "item_sku": "C"},
        ])
    engine.dispose()
    yield url
    os.remove(path)


def test_composite_key_gives_unique_record_ids(sqlite_url) -> None:
    recs = list(SqlConnector(sqlite_url, "supply_chain",
                             ["po_number", "line_number"]).extract())

    ids = [r.source.record_id for r in recs]
    assert sorted(ids) == ["PO1|1", "PO1|2", "PO2|1"]


def test_single_key_string_unchanged(sqlite_url) -> None:
    recs = list(SqlConnector(sqlite_url, "supply_chain", "item_sku").extract())
    assert sorted(r.source.record_id for r in recs) == ["A", "B", "C"]


def test_single_key_list_same_as_string(sqlite_url) -> None:
    recs = list(SqlConnector(sqlite_url, "supply_chain", ["item_sku"]).extract())
    assert sorted(r.source.record_id for r in recs) == ["A", "B", "C"]


def test_pipe_in_values_cannot_collide() -> None:
    conn = SqlConnector("sqlite://", "t", ["a", "b"])
    left = conn._record_id({"a": "x|y", "b": "z"})
    right = conn._record_id({"a": "x", "b": "y|z"})
    assert left != right
    assert left == "x\\|y|z"


def test_empty_key_rejected() -> None:
    with pytest.raises(ValueError):
        SqlConnector("sqlite://", "t", [])
