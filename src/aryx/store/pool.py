"""Shared psycopg3 connection pool — one per DSN, process-scoped (G12)."""
from __future__ import annotations

import logging

from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

_pools: dict[str, ConnectionPool] = {}


def get_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> ConnectionPool:
    """Return a cached ConnectionPool for the given DSN.

    Creates a new pool on first call for a given DSN; subsequent calls for the
    same DSN return the cached instance. Thread-safe via GIL for the dict check.
    """
    if dsn not in _pools:
        logger.info("pool: creating min=%d max=%d", min_size, max_size)
        _pools[dsn] = ConnectionPool(
            conninfo=dsn, min_size=min_size, max_size=max_size, open=True,
        )
    return _pools[dsn]


def close_all() -> None:
    """Close every cached pool and clear the registry (call at shutdown)."""
    for pool in list(_pools.values()):
        try:
            pool.close()
        except Exception:  # noqa: BLE001
            pass
    _pools.clear()
    logger.info("pool: all pools closed")
