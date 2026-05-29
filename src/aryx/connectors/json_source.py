"""JSON source connector: JSONPath-flatten → RawRecord stream (Inc 8, DB path)."""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from aryx.connectors.base import Connector
from aryx.models import RawRecord, SourceRef

logger = logging.getLogger(__name__)


class JsonConnector(Connector):
    """Flattens a JSON file (object or array of objects) into RawRecords.

    Nested dicts are flattened with dot notation (a.b.c); arrays and nested
    objects are JSON-stringified so every value is a scalar in the payload.
    """

    def __init__(self, path: Path, system: str = "json") -> None:
        self._path = path
        self._system = system

    def extract(self) -> Iterator[RawRecord]:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else [data]
        for record in records:
            flat = _flatten(record)
            record_id = _stable_id(record)
            yield RawRecord(
                source=SourceRef(
                    system=self._system,
                    dataset=self._path.stem,
                    record_id=record_id,
                ),
                payload=flat,
            )
        logger.info("json extracted path=%s records=%d", self._path.name, len(records))


def _flatten(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, val in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            result.update(_flatten(val, full_key))
        elif isinstance(val, list):
            result[full_key] = json.dumps(val)
        else:
            result[full_key] = val
    return result


def _stable_id(record: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
