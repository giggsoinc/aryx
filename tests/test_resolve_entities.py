"""Regression: materialize_one_per_record must not claim certainty (DEC-006).

Found via raven-review of the DEC-011 transactional bypass: the bypass
hardcoded confidence=1.0 for every entity it created, but DEC-006 clamps
all cluster confidence to [0.5, 0.99] specifically so nothing ever claims
certainty — skipping the resolution funnel means no evidence was gathered
for the row at all, which is the opposite of certain.
"""
from __future__ import annotations

from aryx.models import ResolutionRecord
from aryx.resolve_entities import materialize_one_per_record


class _FakeEntityStore:
    """Minimal EntityStore stand-in — just enough for landed_records/save."""

    def __init__(self, records: list[ResolutionRecord]) -> None:
        self._records = records
        self.saved = None

    def landed_records(self, run_id: int, key_attrs: list[str]) -> list[ResolutionRecord]:
        return self._records

    def save(self, results: list) -> int:
        self.saved = results
        return len(results)


def test_materialize_one_per_record_confidence_matches_dec006_singleton_floor() -> None:
    records = [ResolutionRecord(record_id=1, text="O1",
                                payload={"order_id": "O1", "company": "Acme"})]
    store = _FakeEntityStore(records)

    materialize_one_per_record(1, "Order", ["order_id"], store)

    (entity, members), = store.saved
    assert entity.confidence == 0.5
    assert entity.confidence < 1.0
    assert members[0].landed_record_id == 1


def test_materialize_one_per_record_confidence_same_for_every_row() -> None:
    records = [
        ResolutionRecord(record_id=i, text=f"O{i}", payload={"order_id": f"O{i}"})
        for i in range(1, 4)
    ]
    store = _FakeEntityStore(records)

    materialize_one_per_record(1, "Order", ["order_id"], store)

    assert all(entity.confidence == 0.5 for entity, _ in store.saved)
