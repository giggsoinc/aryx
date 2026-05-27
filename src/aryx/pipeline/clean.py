"""Cleaning / normalization stage (stage 2). Deterministic — no LLM."""
from __future__ import annotations

from typing import Any

from aryx.models import CleanRecord, RawRecord


def _normalize_value(value: Any) -> Any:
    """Trim strings and coerce empty strings to None.

    Args:
        value: A raw field value.

    Returns:
        The normalized value (None for blank strings).
    """
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return value


def clean(record: RawRecord) -> CleanRecord:
    """Normalize a raw record's payload deterministically.

    Trims whitespace, nulls out empty strings, and drops keys whose
    value is None after normalization.

    Args:
        record: The raw extracted record.

    Returns:
        A CleanRecord carrying the same provenance.
    """
    normalized = {key: _normalize_value(val) for key, val in record.payload.items()}
    pruned = {key: val for key, val in normalized.items() if val is not None}
    return CleanRecord(source=record.source, payload=pruned)
