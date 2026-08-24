"""Real (no-mock) coverage for sql_source.sample_colvals.

Raven-review finding: sample_colvals had zero direct test coverage — every
existing test mocked it away to test the DEC-011 wiring instead. Uses a
real temp-file SQLite database via SQLAlchemy (no Docker/Postgres needed)
so the actual query-building and row-shaping logic runs for real.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine

from aryx.connectors.sql_source import sample_colvals


@pytest.fixture
def sqlite_url():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    url = f"sqlite:///{path}"
    engine = create_engine(url)
    meta = MetaData()
    orders = Table(
        "orders", meta,
        Column("order_id", String, primary_key=True),
        Column("company", String),
        Column("notes", String),
    )
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(orders.insert(), [
            {"order_id": f"ORD{i}", "company": "Acme",
             "notes": None if i % 2 == 0 else "ok"}
            for i in range(5)
        ])
    engine.dispose()
    yield url
    os.remove(path)


def test_sample_colvals_returns_column_to_stringified_values(sqlite_url) -> None:
    colvals = sample_colvals(sqlite_url, "orders")

    assert colvals["order_id"] == [f"ORD{i}" for i in range(5)]
    assert colvals["company"] == ["Acme"] * 5


def test_sample_colvals_drops_null_values_instead_of_stringifying_none(sqlite_url) -> None:
    colvals = sample_colvals(sqlite_url, "orders")

    # i in range(5): notes is None for even i (0,2,4), "ok" for odd i (1,3)
    assert colvals["notes"] == ["ok", "ok"]


def test_sample_colvals_respects_limit(sqlite_url) -> None:
    colvals = sample_colvals(sqlite_url, "orders", limit=2)

    assert colvals["order_id"] == ["ORD0", "ORD1"]
