"""Apply SQL migrations in lexical order. Idempotent (DDL uses IF NOT EXISTS)."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import psycopg

from aryx.queries import load
from aryx.raven_log_config import log as raven_log

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# DSNs already migrated by this process. Many request handlers call
# apply_migrations; without this every request would take the global advisory
# lock and re-run every file, so concurrent ingests would queue behind each
# other. The lock below still guards cross-process DDL.
_APPLIED: set[str] = set()
_APPLIED_LOCK = threading.Lock()

# Set by apply_migrations(force=True) while it holds _APPLIED_LOCK, so _run can
# ignore the aryx_schema_migration records and re-run every file. A module flag
# (not a _run argument) keeps _run(dsn) callable with one argument, which the
# existing tests rely on when they replace it.
_force_rerun = False

# SQLSTATEs for "already exists". Some older migrations are not idempotent and
# hit these on every re-run; they mean the object is there, so they must not
# stop a run from counting as clean.
_ALREADY_EXISTS = frozenset({
    "42P07",  # duplicate_table (also relations such as indexes and constraints)
    "42710",  # duplicate_object
    "42701",  # duplicate_column
    "42723",  # duplicate_function
    "42P06",  # duplicate_schema
    "42712",  # duplicate_alias
})

# SQLSTATE classes that mean the server or connection had a problem, not that
# one statement is unsupported: 08 connection, 40 rollback (deadlock), 53 out of
# resources, 55 object not in prerequisite state (lock not available), 57
# operator intervention (shutdown, cancelled). They abort the pass instead of
# being skipped, so a half-applied schema is never remembered as done.
_TRANSIENT_CLASSES = ("08", "40", "53", "55", "57")


def _is_transient(exc: psycopg.Error, conn: psycopg.Connection) -> bool:
    """True if ``exc`` says the connection or server failed, not the statement."""
    if conn.closed or conn.broken or exc.sqlstate is None:
        return True
    return exc.sqlstate.startswith(_TRANSIENT_CLASSES)


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
    advisory lock. One full pass is remembered whatever its outcome: a
    statement that cannot run (for example ``CREATE EXTENSION`` on a server
    without that extension) is logged once and retried at the next process
    start, not on every request. A run that raises, including a lost
    connection or other transient server error, is not remembered.

    Files that ran cleanly are also recorded in ``aryx_schema_migration``, and a
    recorded file is never run again — not even by a later process. Before this,
    every process start re-ran every file, and migration 0009 rewound the
    workspace id sequence each time, so a deleted workspace's id was handed to
    the next one created (and a still-running orphaned job wrote into it).
    Because of that, an applied migration must never be edited: add a new
    numbered file instead (see migrations/README.md).

    Args:
        dsn: PostgreSQL connection string.
        force: Run again even if this process already migrated the DSN, and
            ignore the recorded files so every file runs. Tests that recreate
            dropped objects use it; the app never needs to.
    """
    global _force_rerun
    with _APPLIED_LOCK:
        if not force and dsn in _APPLIED:
            return
        _force_rerun = force
        try:
            skipped = _run(dsn)
        finally:
            _force_rerun = False
        _APPLIED.add(dsn)
        if skipped:
            logger.warning("migrations finished with %d skipped statement(s); "
                           "they are not retried until this process restarts", skipped)


def _run(dsn: str) -> int:
    """Apply every .sql file under migrations/ in lexical order.

    Statements are split on ';' (respecting dollar-quoted DO blocks) and run
    one at a time, since psycopg runs a single statement per call.

    A session-level advisory lock serialises concurrent callers in other
    processes (the API migrates at startup while the worker and the CLI also
    do), so two processes never run the same DDL at once. The lock dies with
    the connection, so a crashed caller cannot leave it held.

    Args:
        dsn: PostgreSQL connection string.

    Returns:
        How many statements were skipped after an error other than "already
        exists" (0 when every statement ran or the object was already there).
    """
    skipped = 0
    unrecorded: list[str] = []
    files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(load("lock_migrations"))
        try:
            conn.execute(load("create_schema_migration_table"))
            recorded: set[str] = set()
            if not _force_rerun:
                recorded = {row[0] for row in
                            conn.execute(load("select_applied_migrations")).fetchall()}
            for path in files:
                if path.name in recorded:
                    continue
                raw = path.read_text(encoding="utf-8")
                # Strip line comments first so a ';' inside a comment can't be
                # mistaken for a statement separator.
                code = "\n".join(line.split("--", 1)[0] for line in raw.splitlines())
                statements = _split_statements(code)
                file_skipped = 0
                with conn.cursor() as cur:
                    for statement in statements:
                        try:
                            cur.execute(statement)  # type: ignore[arg-type]
                        except psycopg.Error as exc:
                            # An optional/unavailable feature (e.g. a missing
                            # extension) must not block unrelated later migrations.
                            if _is_transient(exc, conn):
                                raise
                            if exc.sqlstate in _ALREADY_EXISTS:
                                logger.debug("migration object already exists file=%s error=%s",
                                             path.name, exc)
                                continue
                            file_skipped += 1
                            logger.warning("migration statement skipped file=%s error=%s",
                                           path.name, exc)
                skipped += file_skipped
                logger.info("migration applied file=%s statements=%d skipped=%d",
                            path.name, len(statements), file_skipped)
                if file_skipped:
                    unrecorded.append(path.name)
                else:
                    conn.execute(load("record_applied_migration"), (path.name,))
        finally:
            # A dead connection already dropped the session lock, and unlocking
            # on it would mask the real error.
            if not (conn.closed or conn.broken):
                conn.execute(load("unlock_migrations"))
    if unrecorded:
        raven_log(
            "WARN", "migration files left unrecorded (retried at next process start)",
            criticality="P3", service="aryx-api", error_code="MIGRATION_UNRECORDED",
            context={"dependency_name": "postgres", "operation": "apply_migrations",
                     "result": "partial", "files": unrecorded,
                     "final_status": "unrecorded", "reason_code": "MIGRATION_UNRECORDED"})
    return skipped
