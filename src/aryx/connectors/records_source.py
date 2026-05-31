"""Connector that yields a pre-built list of RawRecords (no source re-read).

Used by the document self-discovery flow: mentions are extracted once during
the read step, then a confirmed subset is ingested without re-reading the files.
"""
from __future__ import annotations

from collections.abc import Iterator

from aryx.connectors.base import Connector
from aryx.models import RawRecord


class RecordsConnector(Connector):
    """Replays an in-memory list of RawRecords into the pipeline."""

    def __init__(self, records: list[RawRecord]) -> None:
        self._records = records

    def extract(self) -> Iterator[RawRecord]:
        yield from self._records
