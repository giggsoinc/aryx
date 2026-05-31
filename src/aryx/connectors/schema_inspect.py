"""Introspect any SQLAlchemy-reachable database: tables, columns, PK, FK.

Works across Postgres, MySQL/MariaDB, Oracle, and SQLite via SQLAlchemy's
dialect-agnostic Inspector — no per-database SQL.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import create_engine, inspect

logger = logging.getLogger(__name__)


def test_connection(url: str) -> None:
    """Open and close a connection; raises on failure."""
    engine = create_engine(url)
    try:
        with engine.connect():
            pass
    finally:
        engine.dispose()


def introspect(url: str, max_tables: int = 200) -> list[dict[str, Any]]:
    """Return per-table {table, columns, pk, fks} for every base table.

    Aryx's own operational tables (aryx_*) are skipped — they are never
    ingestion targets and would only bloat the discovery prompt.
    """
    engine = create_engine(url)
    out: list[dict[str, Any]] = []
    try:
        insp = inspect(engine)
        names = [t for t in insp.get_table_names() if not t.startswith("aryx_")]
        for table in names[:max_tables]:
            columns = [c["name"] for c in insp.get_columns(table)]
            pk = insp.get_pk_constraint(table).get("constrained_columns", []) or []
            fks = [
                {
                    "column": fk["constrained_columns"][0],
                    "ref_table": fk["referred_table"],
                    "ref_column": fk["referred_columns"][0],
                }
                for fk in insp.get_foreign_keys(table)
                if fk.get("constrained_columns") and fk.get("referred_columns")
            ]
            out.append({"table": table, "columns": columns, "pk": pk, "fks": fks})
    finally:
        engine.dispose()
    logger.info("introspected url-dialect tables=%d", len(out))
    return out
