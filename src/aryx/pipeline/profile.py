"""Profiling stage (stage 3): per-field stats. Incremental and memory-bounded.

Uses an accumulator so profiling never requires the full dataset in memory —
the difference between "slows at TB scale" and "crashes at TB scale".
"""
from __future__ import annotations

from collections.abc import Iterable

from aryx.models import CleanRecord, FieldProfile

_MAX_SAMPLES = 5
# Cap distinct tracking so a high-cardinality field can't grow memory without
# bound. Beyond the cap we report distinct as a floor and flag it.
_DISTINCT_CAP = 10_000


class ProfileAccumulator:
    """Builds field profiles record-by-record with bounded memory."""

    def __init__(self) -> None:
        """Initialize empty per-field accumulators."""
        self._non_null: dict[str, int] = {}
        self._distinct: dict[str, set[str]] = {}
        self._capped: set[str] = set()
        self._samples: dict[str, list[str]] = {}

    def add(self, record: CleanRecord) -> None:
        """Fold one clean record into the running profile.

        Args:
            record: A cleaned record to incorporate.
        """
        for field, value in record.payload.items():
            text = str(value)
            self._non_null[field] = self._non_null.get(field, 0) + 1
            if field not in self._capped:
                seen = self._distinct.setdefault(field, set())
                seen.add(text)
                if len(seen) >= _DISTINCT_CAP:
                    self._capped.add(field)
            bucket = self._samples.setdefault(field, [])
            if len(bucket) < _MAX_SAMPLES and text not in bucket:
                bucket.append(text)

    def result(self) -> list[FieldProfile]:
        """Return one FieldProfile per field observed so far."""
        return [
            FieldProfile(
                field=field,
                non_null=self._non_null[field],
                distinct=len(self._distinct.get(field, set())),
                distinct_capped=field in self._capped,
                samples=self._samples.get(field, []),
            )
            for field in self._non_null
        ]


def profile(records: Iterable[CleanRecord]) -> list[FieldProfile]:
    """Profile a (small) in-memory batch via the accumulator.

    Args:
        records: An iterable of cleaned records.

    Returns:
        Per-field profiles feeding the LLM tagging stage.
    """
    acc = ProfileAccumulator()
    for record in records:
        acc.add(record)
    return acc.result()
