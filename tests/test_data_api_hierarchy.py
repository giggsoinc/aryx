from __future__ import annotations

from aryx.api.data_api import _materialize_hierarchy


class _UnusedStore:
    pass


def test_materialize_hierarchy_refuses_same_type_parent() -> None:
    entities = [
        (10, "Transaction", {"account_key": "A-1", "name": "T-1"}),
        (11, "Transaction", {"account_key": "A-1", "name": "T-2"}),
    ]

    result = _materialize_hierarchy(
        _UnusedStore(), entities, "account_key", None)

    assert result["created_hubs"] == 0
    assert result["created_edges"] == 0
    assert "distinct parent type" in result["error"]
