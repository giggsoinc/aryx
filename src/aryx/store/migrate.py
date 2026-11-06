"""Apply SQL migrations in lexical order. Idempotent (DDL uses IF NOT EXISTS)."""
from __future__ import annotations

import logging
from pathlib import Path

import psycopg
from psycopg.errors import DuplicateColumn, DuplicateObject, DuplicateTable

from aryx.queries import load

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_LOCK_KEY = 0x41525958  # "ARYX" — advisory lock id serialising migrators
_applied_dsns: set[str] = set()  # DSNs fully migrated by this process
# Errors meaning "this change already exists" — e.g. 0027's ADD CONSTRAINT.
_ALREADY_APPLIED = (DuplicateColumn, DuplicateObject, DuplicateTable)


def _split_statements(sql: str) -> list[str]:
    """Split on ';' but never inside a $tag$...$tag$ dollar-quoted block.

    Lets migrations use PL/pgSQL DO blocks (whose bodies contain semicolons)
    without the naive split tearing them apart.
    """
    out: list[str] = []
    buf: list[str] = []
    tag: str | None = None
    i, n = 0, len(sql)
    while i < n:
        if tag is not None:
            if sql.startswith(tag, i):
                buf.append(tag)
                i += len(tag)
                tag = None
            else:
                buf.append(sql[i])
                i += 1
            continue
        if sql[i] == "$":
            close = sql.find("$", i + 1)
            inner = sql[i + 1:close] if close != -1 else None
            if inner is not None and (inner == "" or inner.isidentifier()):
                tag = sql[i:close + 1]
                buf.append(tag)
                i = close + 1
                continue
        if sql[i] == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(sql[i])
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def apply_migrations(dsn: str) -> None:
    """Apply every .sql file under migrations/ in lexical order.

    Statements are split on ';' (respecting dollar-quoted DO blocks) and run
    one at a time, since psycopg runs a single statement per call.

    Applied files are recorded in ``aryx_schema_migration`` and never re-run.
    Previously every call re-executed every file; migration 0009 then rewound
    the workspace id sequence on each call, so a deleted workspace's id was
    handed to the next one created (and a still-running orphaned job wrote
    into it). A file is recorded only when ALL its statements succeeded, so a
    migration with an optional/unavailable feature is retried as before. A
    process-level cache makes the call a no-op once everything is applied,
    and a Postgres advisory lock serialises concurrent starters.

    Args:
        dsn: PostgreSQL connection string.
    """
    if dsn in _applied_dsns:
        return
    files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    all_clean = True
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(load("acquire_migration_lock"), (_LOCK_KEY,))
        try:
            conn.execute(load("create_schema_migration_table"))
            applied = {row[0] for row in
                       conn.execute(load("select_applied_migrations")).fetchall()}
            for path in files:
                if path.name in applied:
                    continue
                raw = path.read_text(encoding="utf-8")
                # Strip line comments first so a ';' inside a comment can't be
                # mistaken for a statement separator.
                code = "\n".join(line.split("--", 1)[0] for line in raw.splitlines())
                statements = _split_statements(code)
                failed = 0
                with conn.cursor() as cur:
                    for statement in statements:
                        try:
                            cur.execute(statement)  # type: ignore[arg-type]
                        except _ALREADY_APPLIED as exc:
                            # "already exists": the change is already in place
                            # (these files were re-run on every call before
                            # tracking), so the statement counts as applied.
                            logger.info("migration statement already applied file=%s error=%s",
                                        path.name, exc)
                        except psycopg.Error as exc:
                            # An optional/unavailable feature (e.g. a missing
                            # extension) must not block unrelated later migrations.
                            failed += 1
                            logger.warning("migration statement skipped file=%s error=%s",
                                           path.name, exc)
                logger.info("migration applied file=%s statements=%d failed=%d",
                            path.name, len(statements), failed)
                if failed:
                    all_clean = False
                else:
                    conn.execute(load("record_applied_migration"), (path.name,))
        finally:
            conn.execute(load("release_migration_lock"), (_LOCK_KEY,))
    if all_clean:
        _applied_dsns.add(dsn)
