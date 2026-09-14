"""Tests for UnstructuredDashboardStore — fake-pool convention (test_stores.py)."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch


class _Cursor:
    def __init__(self, fetchone=None, fetchall=None):
        self._fetchone = fetchone
        self._fetchall = fetchall or []
        self.calls: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query, params=()):
        self.calls.append((query, params))

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def cursor(self):
        return self._cursor


class _Pool:
    def __init__(self, cursor):
        self._cursor = cursor

    def connection(self):
        return _Conn(self._cursor)


def _patched(cursor: _Cursor):
    return patch("aryx.store.unstructured_dashboard_store.get_pool",
                 return_value=_Pool(cursor))


def test_has_document_data_true():
    from aryx.store.unstructured_dashboard_store import UnstructuredDashboardStore
    cursor = _Cursor(fetchone=(True,))
    with _patched(cursor):
        store = UnstructuredDashboardStore("dsn", workspace_id=7)
        assert store.has_document_data() is True
    assert cursor.calls[0][1] == (7,)


def test_has_document_data_false_when_no_row():
    from aryx.store.unstructured_dashboard_store import UnstructuredDashboardStore
    cursor = _Cursor(fetchone=None)
    with _patched(cursor):
        assert UnstructuredDashboardStore("dsn").has_document_data() is False


def test_top_document_entities_maps_rows_and_passes_params():
    from aryx.store.unstructured_dashboard_store import UnstructuredDashboardStore
    rows = [("Person", "Jane Doe", 12), ("Organization", "Acme Corp", 5)]
    cursor = _Cursor(fetchall=rows)
    with _patched(cursor):
        store = UnstructuredDashboardStore("dsn", workspace_id=3)
        result = store.top_document_entities(limit=10, min_count=4)
    assert result == [
        {"ontology_type": "Person", "name": "Jane Doe", "count": 12},
        {"ontology_type": "Organization", "name": "Acme Corp", "count": 5},
    ]
    assert cursor.calls[0][1] == (3, 4, 10)


def test_top_document_entities_empty_when_no_rows():
    from aryx.store.unstructured_dashboard_store import UnstructuredDashboardStore
    cursor = _Cursor(fetchall=[])
    with _patched(cursor):
        assert UnstructuredDashboardStore("dsn").top_document_entities() == []


def test_entity_timeline_maps_rows_and_passes_workspace_param():
    from aryx.store.unstructured_dashboard_store import UnstructuredDashboardStore
    rows = [(date(2026, 9, 1), 3), (date(2026, 9, 2), 7)]
    cursor = _Cursor(fetchall=rows)
    with _patched(cursor):
        store = UnstructuredDashboardStore("dsn", workspace_id=5)
        result = store.entity_timeline()
    assert result == [
        {"date": "2026-09-01", "count": 3},
        {"date": "2026-09-02", "count": 7},
    ]
    assert cursor.calls[0][1] == (5,)


def test_entity_timeline_empty_when_no_rows():
    from aryx.store.unstructured_dashboard_store import UnstructuredDashboardStore
    cursor = _Cursor(fetchall=[])
    with _patched(cursor):
        assert UnstructuredDashboardStore("dsn").entity_timeline() == []


def test_entity_excerpts_maps_rows_and_passes_params():
    from aryx.store.unstructured_dashboard_store import UnstructuredDashboardStore
    rows = [("Longest excerpt here.",), ("Shorter one.",)]
    cursor = _Cursor(fetchall=rows)
    with _patched(cursor):
        store = UnstructuredDashboardStore("dsn", workspace_id=9)
        result = store.entity_excerpts("Person", "Jane Doe", limit=3)
    assert result == ["Longest excerpt here.", "Shorter one."]
    assert cursor.calls[0][1] == (9, "Person", "Jane Doe", 3)


def test_entity_excerpts_empty_when_no_rows():
    from aryx.store.unstructured_dashboard_store import UnstructuredDashboardStore
    cursor = _Cursor(fetchall=[])
    with _patched(cursor):
        assert UnstructuredDashboardStore("dsn").entity_excerpts("Person", "Nobody") == []


def test_close_is_a_noop():
    from aryx.store.unstructured_dashboard_store import UnstructuredDashboardStore
    cursor = _Cursor()
    with _patched(cursor):
        UnstructuredDashboardStore("dsn").close()
