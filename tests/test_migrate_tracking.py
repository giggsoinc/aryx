"""Unit tests for applied-migration tracking and the workspace id sequence.

Bug 3 of the report: migrations re-ran and migration 0009 rewound the
workspace id sequence to max(id) each time, so a deleted workspace's id was
handed to the next one created. Applied files are now recorded in
``aryx_schema_migration`` and never re-run (the per-process memo and the
advisory lock live in ``aryx.store.migrate`` already; see test_migrate_once).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aryx.store import migrate

_MIGRATIONS = Path(migrate.__file__).parent / "migrations"


class _Unsupported(migrate.psycopg.Error):
    sqlstate = "0A000"  # e.g. an optional extension is not available


class _DuplicateTable(migrate.psycopg.Error):
    sqlstate = "42P07"  # what Postgres reports for "relation already exists"


class _Result:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class _Cur:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn

    def __enter__(self) -> "_Cur":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def execute(self, statement: str, params: Any = None) -> None:
        self._conn.run(statement, params)


class _Conn:
    """Records every statement; remembers recorded migrations across connects."""

    recorded: set[str] = set()
    log: list[str] = []
    fail_on: str | None = None
    fail_exc: type[Exception] = _Unsupported
    closed = False
    broken = False

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def cursor(self) -> _Cur:
        return _Cur(self)

    def execute(self, statement: str, params: Any = None) -> _Result:
        return self.run(statement, params)

    def run(self, statement: str, params: Any = None) -> _Result:
        type(self).log.append(statement)
        if statement.startswith("SELECT filename FROM aryx_schema_migration"):
            return _Result([(f,) for f in sorted(type(self).recorded)])
        if statement.startswith("INSERT INTO aryx_schema_migration"):
            type(self).recorded.add(params[0])
        fail = type(self).fail_on
        if fail and fail in statement:
            raise type(self).fail_exc("boom")
        return _Result([])


@pytest.fixture(autouse=True)
def _fake_psycopg(monkeypatch: pytest.MonkeyPatch) -> None:
    _Conn.recorded, _Conn.log, _Conn.fail_on = set(), [], None
    _Conn.fail_exc = _Unsupported
    monkeypatch.setattr(migrate, "_APPLIED", set())
    monkeypatch.setattr(migrate.psycopg, "connect",
                        lambda dsn, autocommit=True: _Conn())


def _all_files() -> set[str]:
    return {p.name for p in _MIGRATIONS.glob("*.sql")}


def test_every_migration_is_recorded_after_the_first_run() -> None:
    migrate.apply_migrations("dsn-a")
    assert _Conn.recorded == _all_files()


def test_second_call_runs_nothing_at_all() -> None:
    migrate.apply_migrations("dsn-b")
    _Conn.log.clear()
    migrate.apply_migrations("dsn-b")
    assert _Conn.log == []  # process memo: not even a connection


def test_recorded_migrations_are_skipped_by_a_new_process() -> None:
    migrate.apply_migrations("dsn-c")
    migrate._APPLIED.clear()  # simulate a restart: DB still has the records
    _Conn.log.clear()
    migrate.apply_migrations("dsn-c")
    assert not any("aryx_workspace" in s for s in _Conn.log), (
        "0009 must not run again once recorded")


def test_workspace_migration_is_not_rerun_after_a_delete() -> None:
    """Regression: re-running 0009 after a delete rewound the id sequence."""
    migrate.apply_migrations("dsn-d")
    migrate._APPLIED.clear()
    _Conn.log.clear()
    migrate.apply_migrations("dsn-d")
    assert not [s for s in _Conn.log if "setval" in s]


def test_force_ignores_the_records_and_reruns_every_file() -> None:
    """Tests that recreate dropped objects rely on force=True re-running all files."""
    migrate.apply_migrations("dsn-i")
    _Conn.log.clear()
    migrate.apply_migrations("dsn-i", force=True)
    assert any("setval" in s for s in _Conn.log)
    migrate._APPLIED.clear()
    _Conn.log.clear()
    migrate.apply_migrations("dsn-i")  # the flag does not leak into later calls
    assert not any("setval" in s for s in _Conn.log)


def test_a_file_with_a_failing_statement_is_not_recorded() -> None:
    # Simulate an optional feature failing inside one migration (0009 here).
    _Conn.fail_on = "CREATE TABLE IF NOT EXISTS aryx_workspace ("
    migrate.apply_migrations("dsn-e")
    assert "0009_workspaces.sql" not in _Conn.recorded
    assert "0001_init.sql" in _Conn.recorded  # unrelated files still recorded


def test_a_permanently_failing_file_does_not_cost_a_pass_per_request() -> None:
    """Review M1: one never-succeeding file must not make every request take the
    advisory lock and re-run it. After one full pass the DSN is remembered; the
    unrecorded file is retried at the next process start only."""
    _Conn.fail_on = "CREATE TABLE IF NOT EXISTS aryx_workspace ("
    migrate.apply_migrations("dsn-h")
    assert "dsn-h" in migrate._APPLIED
    _Conn.log.clear()
    migrate.apply_migrations("dsn-h")  # a later request
    assert _Conn.log == []

    migrate._APPLIED.clear()  # simulate the next process start
    _Conn.fail_on = None
    migrate.apply_migrations("dsn-h")
    assert "0009_workspaces.sql" in _Conn.recorded  # retried, now succeeds


def test_already_exists_errors_count_as_applied() -> None:
    """0027's ADD CONSTRAINT fails with 'already exists' — that is not a failure."""
    _Conn.fail_on = "CREATE TABLE IF NOT EXISTS aryx_workspace ("
    _Conn.fail_exc = _DuplicateTable
    migrate.apply_migrations("dsn-g")
    assert "0009_workspaces.sql" in _Conn.recorded


def test_advisory_lock_is_taken_and_released() -> None:
    migrate.apply_migrations("dsn-f")
    assert any("pg_advisory_lock" in s for s in _Conn.log)
    assert any("pg_advisory_unlock" in s for s in _Conn.log)


def test_0009_sequence_reset_can_only_move_forward() -> None:
    text = (_MIGRATIONS / "0009_workspaces.sql").read_text(encoding="utf-8")
    code = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    assert "GREATEST(" in code
    assert "pg_sequences" in code and "last_value" in code
