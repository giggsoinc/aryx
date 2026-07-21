from __future__ import annotations

from aryx.store import job_store


class _Cursor:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount
        self.calls: list[tuple[str, tuple]] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: tuple) -> None:
        self.calls.append((query, params))


class _Conn:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self._cursor


class _Pool:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def connection(self) -> _Conn:
        return _Conn(self._cursor)


def test_update_stage_skips_event_when_terminal_job_ignored(monkeypatch) -> None:
    cursor = _Cursor(rowcount=0)
    monkeypatch.setattr(job_store, "get_pool", lambda _dsn: _Pool(cursor))

    job_store.JobStore("dsn").update_stage("job-1", "Resolve", 50, "working")

    assert len(cursor.calls) == 1
    assert "UPDATE aryx_job" in cursor.calls[0][0]


def test_update_stage_writes_event_when_job_updates(monkeypatch) -> None:
    cursor = _Cursor(rowcount=1)
    monkeypatch.setattr(job_store, "get_pool", lambda _dsn: _Pool(cursor))

    job_store.JobStore("dsn").update_stage("job-1", "Resolve", 50, "working")

    assert len(cursor.calls) == 2
    assert "UPDATE aryx_job" in cursor.calls[0][0]
    assert "INSERT INTO aryx_job_event" in cursor.calls[1][0]
