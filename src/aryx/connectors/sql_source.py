"""Generic SQL source connector (any SQLAlchemy dialect) → RawRecord stream.

Table reflection gives dialect-correct identifier quoting, so the same code
streams rows from Postgres, MySQL, Oracle, or SQLite.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import MetaData, Table, create_engine, select

from aryx.connectors.base import Connector
from aryx.models import RawRecord, SourceRef

logger = logging.getLogger(__name__)

_NATIVE = (int, float, str, bool, type(None))


def _coerce(value: object) -> object:
    """Keep JSON-native values; stringify dates/Decimals/etc. for JSONB landing."""
    return value if isinstance(value, _NATIVE) else str(value)


class SqlConnector(Connector):
    """Stream rows of one table from any SQLAlchemy-reachable database."""

    def __init__(self, url: str, table: str, key_column: str,
                 system: str = "rdb") -> None:
        """Configure for one table on a given connection URL."""
        self._url = url
        self._table = table
        self._key = key_column
        self._system = system

    def extract(self) -> Iterator[RawRecord]:
        """Yield each row as a RawRecord with provenance."""
        engine = create_engine(self._url)
        count = 0
        try:
            tbl = Table(self._table, MetaData(), autoload_with=engine)
            with engine.connect() as conn:
                result = conn.execution_options(stream_results=True).execute(select(tbl))
                for row in result.mappings():
                    payload = {k: _coerce(v) for k, v in row.items()}
                    yield RawRecord(
                        source=SourceRef(
                            system=self._system, dataset=self._table,
                            record_id=str(payload.get(self._key, "")),
                        ),
                        payload=payload,
                    )
                    count += 1
        finally:
            engine.dispose()
        logger.info("sql extracted table=%s records=%d", self._table, count)
