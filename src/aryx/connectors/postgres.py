"""PostgreSQL source connector (pipeline stage 1)."""
from __future__ import annotations

import logging
from collections.abc import Iterator

import psycopg
from psycopg import sql

from aryx.connectors.base import Connector
from aryx.models import RawRecord, SourceRef
from aryx.queries import load

logger = logging.getLogger(__name__)


class PostgresConnector(Connector):
    """Extract rows from a single PostgreSQL table as RawRecords."""

    def __init__(
        self,
        dsn: str,
        table: str,
        key_column: str,
        batch_size: int = 500,
    ) -> None:
        """Configure the connector for one table.

        Args:
            dsn: PostgreSQL connection string.
            table: Table name to extract (passed as a safe identifier).
            key_column: Column used as the provenance record id.
            batch_size: Server-side cursor fetch size.
        """
        self._dsn = dsn
        self._table = table
        self._key = key_column
        self._batch_size = batch_size

    def extract(self) -> Iterator[RawRecord]:
        """Stream rows from the configured table as RawRecords."""
        # SQL text lives in queries/select_all.sql; the table name is bound
        # via sql.Identifier — never string-formatted into the statement.
        query = sql.SQL(load("select_all")).format(table=sql.Identifier(self._table))
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor(name="aryx_extract") as cur:
                cur.itersize = self._batch_size
                cur.execute(query)
                columns = [d.name for d in cur.description or []]
                for row in cur:
                    payload = dict(zip(columns, row))
                    yield RawRecord(
                        source=SourceRef(
                            system="postgresql",
                            dataset=self._table,
                            record_id=str(payload.get(self._key, "")),
                        ),
                        payload=payload,
                    )
        logger.info("postgres extract complete table=%s", self._table)
