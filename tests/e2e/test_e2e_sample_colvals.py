"""Real-Postgres coverage for connectors.postgres.sample_colvals.

Raven-review finding: sample_colvals had zero direct test coverage — every
existing test mocked it away to test the DEC-011 wiring instead. Creates a
real temp table in the e2e Postgres instance and queries it for real,
including the safe-identifier binding (sql.Identifier) that makes an
arbitrary table name safe to interpolate.
"""
from __future__ import annotations

import uuid

import psycopg
import pytest

from aryx.connectors.postgres import sample_colvals

pytestmark = pytest.mark.e2e


@pytest.fixture
def orders_table(e2e_dsn):
    table = f"e2e_sample_colvals_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(e2e_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'CREATE TABLE "{table}" '
                "(order_id TEXT, company TEXT, notes TEXT)")
            cur.executemany(
                f'INSERT INTO "{table}" (order_id, company, notes) '
                "VALUES (%s, %s, %s)",
                [(f"ORD{i}", "Acme", None if i % 2 == 0 else "ok")
                 for i in range(5)],
            )
    yield table
    with psycopg.connect(e2e_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{table}"')


def test_sample_colvals_reads_real_table(e2e_dsn, orders_table) -> None:
    colvals = sample_colvals(e2e_dsn, orders_table)

    assert colvals["order_id"] == [f"ORD{i}" for i in range(5)]
    assert colvals["company"] == ["Acme"] * 5
    assert colvals["notes"] == ["ok", "ok"]  # nulls dropped, not stringified


def test_sample_colvals_respects_limit(e2e_dsn, orders_table) -> None:
    colvals = sample_colvals(e2e_dsn, orders_table, limit=2)

    assert colvals["order_id"] == ["ORD0", "ORD1"]
