"""apply_migrations runs once per process per DSN (review item M1)."""
from __future__ import annotations

import threading

import pytest

from aryx.store import migrate


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(migrate, "_APPLIED", set())
    calls: list[str] = []
    monkeypatch.setattr(migrate, "_run", lambda dsn: calls.append(dsn) or 0)
    return calls


def test_second_call_for_the_same_dsn_does_nothing(_fresh: list[str]) -> None:
    migrate.apply_migrations("dsn-a")
    migrate.apply_migrations("dsn-a")
    assert _fresh == ["dsn-a"]


def test_each_dsn_is_migrated_separately(_fresh: list[str]) -> None:
    migrate.apply_migrations("dsn-a")
    migrate.apply_migrations("dsn-b")
    assert _fresh == ["dsn-a", "dsn-b"]


def test_force_runs_again(_fresh: list[str]) -> None:
    migrate.apply_migrations("dsn-a")
    migrate.apply_migrations("dsn-a", force=True)
    assert _fresh == ["dsn-a", "dsn-a"]


def test_a_failed_run_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []

    def flaky(dsn: str) -> int:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("db down")
        return 0

    monkeypatch.setattr(migrate, "_run", flaky)
    with pytest.raises(RuntimeError):
        migrate.apply_migrations("dsn-a")
    migrate.apply_migrations("dsn-a")
    migrate.apply_migrations("dsn-a")
    assert len(attempts) == 2


def test_parallel_callers_run_it_once(_fresh: list[str]) -> None:
    threads = [threading.Thread(target=migrate.apply_migrations, args=("dsn-a",))
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert _fresh == ["dsn-a"]


def test_a_run_with_skipped_statements_is_remembered_and_logged_once(
        monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    attempts: list[int] = []

    def run(dsn: str) -> int:
        attempts.append(1)
        return 2  # e.g. CREATE EXTENSION and its index on a server without pg_trgm

    monkeypatch.setattr(migrate, "_run", run)
    with caplog.at_level("WARNING", logger=migrate.logger.name):
        for _ in range(5):
            migrate.apply_migrations("dsn-a")
    assert len(attempts) == 1
    done = [r for r in caplog.records if "2 skipped statement(s)" in r.getMessage()]
    assert len(done) == 1
