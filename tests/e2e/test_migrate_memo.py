"""On a healthy database a full re-run counts as clean, so it is remembered.

Some older migrations hit "already exists" on every re-run. If those counted as
skipped statements, apply_migrations would never remember the database and every
request handler would take the global lock again (review item M1).
"""
from __future__ import annotations

import pytest

from aryx.store import migrate

pytestmark = pytest.mark.e2e


def test_a_rerun_on_a_migrated_database_is_clean(e2e_dsn: str) -> None:
    migrate.apply_migrations(e2e_dsn, force=True)
    assert migrate._run(e2e_dsn) is True


def test_second_call_is_skipped_once_remembered(e2e_dsn: str, monkeypatch: pytest.MonkeyPatch) -> None:
    migrate.apply_migrations(e2e_dsn, force=True)
    ran: list[str] = []
    real = migrate._run
    monkeypatch.setattr(migrate, "_run", lambda dsn: ran.append(dsn) or real(dsn))
    migrate.apply_migrations(e2e_dsn)
    migrate.apply_migrations(e2e_dsn)
    assert ran == []
