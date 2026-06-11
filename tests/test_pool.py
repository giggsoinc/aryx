"""Tests for G12: shared connection pool singleton behaviour."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# Stub heavy deps so aryx.store.pool loads without the installed packages
for _mod in ("psycopg", "psycopg.types", "psycopg.types.json",
             "falkordb", "pgvector", "pgvector.psycopg"):
    sys.modules.setdefault(_mod, MagicMock())

_mock_cp = MagicMock()
sys.modules.setdefault("psycopg_pool", MagicMock(ConnectionPool=_mock_cp))


def _fresh_pool_module():
    """Return the pool module with an empty cache."""
    import importlib
    # Force reimport to reset module-level state
    if "aryx.store.pool" in sys.modules:
        del sys.modules["aryx.store.pool"]
    import aryx.store.pool as p
    p._pools.clear()
    return p


def test_same_dsn_returns_same_pool():
    p = _fresh_pool_module()
    with patch.object(p, "ConnectionPool", MagicMock(return_value=MagicMock())) as MockCP:
        pool_a = p.get_pool("postgresql://localhost/db")
        pool_b = p.get_pool("postgresql://localhost/db")
    assert pool_a is pool_b
    assert MockCP.call_count == 1


def test_different_dsn_returns_different_pools():
    p = _fresh_pool_module()
    m1, m2 = MagicMock(), MagicMock()
    with patch.object(p, "ConnectionPool", side_effect=[m1, m2]):
        pool_a = p.get_pool("postgresql://localhost/db1")
        pool_b = p.get_pool("postgresql://localhost/db2")
    assert pool_a is not pool_b


def test_close_all_closes_and_clears():
    p = _fresh_pool_module()
    mock_1, mock_2 = MagicMock(), MagicMock()
    with patch.object(p, "ConnectionPool", side_effect=[mock_1, mock_2]):
        p.get_pool("postgresql://localhost/db1")
        p.get_pool("postgresql://localhost/db2")
        p.close_all()
    mock_1.close.assert_called_once()
    mock_2.close.assert_called_once()
    assert len(p._pools) == 0


def test_get_pool_after_close_all_creates_new():
    p = _fresh_pool_module()
    first, second = MagicMock(), MagicMock()
    with patch.object(p, "ConnectionPool", side_effect=[first, second]):
        p.get_pool("postgresql://localhost/db")
        p.close_all()
        result = p.get_pool("postgresql://localhost/db")
    assert result is second
