"""CSV source connector: each row becomes a RawRecord."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path

from aryx.connectors.base import Connector
from aryx.models import RawRecord, SourceRef

logger = logging.getLogger(__name__)


class CsvConnector(Connector):
    """Read a CSV file (or bytes) into RawRecords, one per row."""

    def __init__(self, source: Path | bytes, system: str = "csv",
                 dataset: str = "upload") -> None:
        self._source = source
        self._system = system
        self._dataset = dataset

    def extract(self) -> Iterator[RawRecord]:
        if isinstance(self._source, bytes):
            reader = csv.DictReader(io.StringIO(self._source.decode("utf-8")))
        else:
            reader = csv.DictReader(self._source.open(encoding="utf-8"))
        count = 0
        for row in reader:
            record_id = hashlib.sha256(
                json.dumps(row, sort_keys=True).encode()
            ).hexdigest()[:16]
            yield RawRecord(
                source=SourceRef(system=self._system, dataset=self._dataset,
                                 record_id=record_id),
                payload=dict(row),
            )
            count += 1
        logger.info("csv extracted dataset=%s records=%d", self._dataset, count)
