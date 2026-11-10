"""A database is migrated once per process, whether or not every statement could run.

Older migrations hit "already exists" on every re-run; that must not count as a
skipped statement. A statement that keeps failing (a missing optional extension,
say) must not make every request redo the whole pass (review items M1 and M1').
"""
from __future__ import annotations

import logging

import pytest

from aryx.store import migrate

pytestmark = pytest.mark.e2e


def test_a_rerun_on_a_migrated_database_is_clean(e2e_dsn: str) -> None:
    migrate.apply_migrations(e2e_dsn, force=True)
    assert migrate._run(e2e_dsn) == 0


def test_second_call_is_skipped_once_remembered(e2e_dsn: str, monkeypatch: pytest.MonkeyPatch) -> None:
    migrate.apply_migrations(e2e_dsn, force=True)
    ran: list[str] = []
    real = migrate._run
    monkeypatch.setattr(migrate, "_run", lambda dsn: ran.append(dsn) or real(dsn))
    migrate.apply_migrations(e2e_dsn)
    migrate.apply_migrations(e2e_dsn)
    assert ran == []


def test_a_statement_that_keeps_failing_is_tried_once_per_process(
        e2e_dsn: str, tmp_path, monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "0001_optional.sql").write_text(
        "CREATE EXTENSION no_such_extension_xyz;\nSELECT 1;\n", encoding="utf-8")
    monkeypatch.setattr(migrate, "_MIGRATIONS_DIR", tmp_path)
    monkeypatch.setattr(migrate, "_APPLIED", set())
    real = migrate._run
    assert real(e2e_dsn) == 1  # the missing extension is skipped, SELECT 1 runs

    ran: list[str] = []
    monkeypatch.setattr(migrate, "_run", lambda dsn: ran.append(dsn) or real(dsn))
    with caplog.at_level(logging.WARNING, logger=migrate.logger.name):
        for _ in range(5):
            migrate.apply_migrations(e2e_dsn)
    assert len(ran) == 1
    assert len([r for r in caplog.records if "finished with 1 skipped" in r.getMessage()]) == 1
