"""Apply SQL migrations in lexical order. Idempotent (DDL uses IF NOT EXISTS)."""
from __future__ import annotations

import logging
from pathlib import Path

import psycopg

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def apply_migrations(dsn: str) -> None:
    """Apply every .sql file under migrations/ in lexical order.

    Statements are split on ';' (the schema contains no embedded semicolons)
    and executed one at a time, since psycopg's extended protocol runs a
    single statement per call.

    Args:
        dsn: PostgreSQL connection string.
    """
    files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in files:
            raw = path.read_text(encoding="utf-8")
            # Strip line comments first so a ';' inside a comment can't be
            # mistaken for a statement separator.
            code = "\n".join(line.split("--", 1)[0] for line in raw.splitlines())
            statements = [stmt.strip() for stmt in code.split(";") if stmt.strip()]
            with conn.cursor() as cur:
                for statement in statements:
                    try:
                        cur.execute(statement)  # type: ignore[arg-type]
                    except psycopg.Error as exc:
                        # An optional/unavailable feature (e.g. a missing
                        # extension) must not block unrelated later migrations.
                        logger.warning("migration statement skipped file=%s error=%s",
                                       path.name, exc)
            logger.info("migration applied file=%s statements=%d", path.name, len(statements))
