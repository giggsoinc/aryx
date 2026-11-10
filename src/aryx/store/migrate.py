"""Apply SQL migrations in lexical order. Idempotent (DDL uses IF NOT EXISTS)."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import psycopg

from aryx.queries import load

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# DSNs already migrated by this process. Many request handlers call
# apply_migrations; without this every request would take the global advisory
# lock and re-run every file, so concurrent ingests would queue behind each
# other. The lock below still guards cross-process DDL.
_APPLIED: set[str] = set()
_APPLIED_LOCK = threading.Lock()


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


def apply_migrations(dsn: str, *, force: bool = False) -> None:
    """Apply every migration once per process for this database.

    The first call for a DSN runs the migrations; later calls return at once,
    so request handlers can keep calling this without queueing on the global
    advisory lock. A failed run is not remembered, so the next call retries.

    Args:
        dsn: PostgreSQL connection string.
        force: Run again even if this process already migrated the DSN. Tests
            that recreate dropped objects use it; the app never needs to.
    """
    with _APPLIED_LOCK:
        if not force and dsn in _APPLIED:
            return
        _run(dsn)
        _APPLIED.add(dsn)


def _run(dsn: str) -> None:
    """Apply every .sql file under migrations/ in lexical order.

    Statements are split on ';' (respecting dollar-quoted DO blocks) and run
    one at a time, since psycopg runs a single statement per call.

    A session-level advisory lock serialises concurrent callers in other
    processes (the API migrates at startup while the worker and the CLI also
    do), so two processes never run the same DDL at once. The lock dies with
    the connection, so a crashed caller cannot leave it held.

    Args:
        dsn: PostgreSQL connection string.
    """
    files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(load("lock_migrations"))
        try:
            for path in files:
                raw = path.read_text(encoding="utf-8")
                # Strip line comments first so a ';' inside a comment can't be
                # mistaken for a statement separator.
                code = "\n".join(line.split("--", 1)[0] for line in raw.splitlines())
                statements = _split_statements(code)
                with conn.cursor() as cur:
                    for statement in statements:
                        try:
                            cur.execute(statement)  # type: ignore[arg-type]
                        except psycopg.Error as exc:
                            # An optional/unavailable feature (e.g. a missing
                            # extension) must not block unrelated later migrations.
                            logger.warning("migration statement skipped file=%s error=%s",
                                           path.name, exc)
                logger.info("migration applied file=%s statements=%d",
                            path.name, len(statements))
        finally:
            conn.execute(load("unlock_migrations"))
