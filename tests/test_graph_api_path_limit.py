"""A runaway shortest-path search is a 422, not a 500 (review item L2)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from aryx.api import graph_api
from aryx.graph.pg_reader import GraphSearchTooLarge


class _Reader:
    def __init__(self, error: Exception | None) -> None:
        self._error = error

    def shortest_path(self, source: int, target: int, max_hops: int) -> list:
        if self._error:
            raise self._error
        return []


def _client(error: Exception | None) -> TestClient:
    app = graph_api.create_app()
    app.dependency_overrides[graph_api._reader] = lambda: _Reader(error)
    return TestClient(app, raise_server_exceptions=False)


def test_search_too_large_is_422_with_a_hint() -> None:
    res = _client(GraphSearchTooLarge("frontier exceeded 50000 entities")).get(
        "/entities/1/path/2")
    assert res.status_code == 422
    assert "lower max_hops" in res.json()["detail"]


def test_no_path_is_still_an_empty_list() -> None:
    res = _client(None).get("/entities/1/path/2")
    assert res.status_code == 200
    assert res.json() == []
