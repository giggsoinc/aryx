"""Tests for G3: confidence-weighted golden record with conflict detection."""
from __future__ import annotations

import logging

import pytest

from aryx.resolution.survivor import survivors
from aryx.resolution.cluster import golden_record, golden_record_weighted


def test_weighted_merge_higher_score_wins():
    payloads = [
        {"email": "alice@old.com", "name": "Alice"},
        {"email": "alice@new.com", "name": "Alice"},
    ]
    record_ids = [1, 2]
    pair_scores = {(1, 2): 0.95}
    result = survivors(payloads, record_ids, pair_scores)
    assert result["name"] == "Alice"
    assert "email" in result


def test_conflict_logs_warning(caplog):
    payloads = [
        {"email": "a@x.com"},
        {"email": "b@x.com"},
    ]
    record_ids = [10, 11]
    pair_scores = {(10, 11): 0.91}
    with caplog.at_level(logging.WARNING, logger="aryx.resolution.survivor"):
        result = survivors(payloads, record_ids, pair_scores)
    assert any("conflict" in r.message for r in caplog.records)
    assert "email" in result


def test_provenance_present():
    payloads = [{"name": "Bob", "city": "NYC"}, {"city": "SF"}]
    record_ids = [5, 6]
    pair_scores = {(5, 6): 0.88}
    result = survivors(payloads, record_ids, pair_scores)
    prov = result["_provenance"]
    assert "name" in prov
    assert "city" in prov
    assert prov["name"] == 5


def test_legacy_fallback_first_non_empty():
    payloads = [{"a": 1, "b": None}, {"a": 99, "b": 2}]
    result = golden_record(payloads)
    assert result["a"] == 1
    assert result["b"] == 2
    assert "_provenance" not in result


def test_single_record_cluster():
    payloads = [{"x": 42, "y": "hello"}]
    record_ids = [7]
    result = survivors(payloads, record_ids, {})
    assert result["x"] == 42
    assert result["y"] == "hello"
    assert result["_provenance"]["x"] == 7


def test_golden_record_weighted_delegates():
    payloads = [{"k": "v1"}, {"k": "v2"}]
    result = golden_record_weighted(payloads, [1, 2], {(1, 2): 0.9})
    assert "k" in result
    assert "_provenance" in result


def test_empty_payloads():
    assert survivors([], [], {}) == {}
