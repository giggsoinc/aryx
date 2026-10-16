"""Regression coverage for a real bug found this session: the shared
synonym-renaming table in llm_normalize.py is applied to EVERY complete_json
schema, not just the entity-extraction ones it was designed for. A schema
that legitimately wants a field named "label" (or "value", "type", "title",
"kind", "category", "score", ...) gets that key silently renamed to its
"canonical" synonym before the caller ever sees it — exactly the same class
of bug tests/test_adjudicate.py documents for "score" -> "confidence".

andie_planner's named_buckets feature hit this live: its bucket items were
originally shaped {"label": ..., "max": ...}, and every real LLM response
arrived with "label" silently renamed to "name", so ground.py's parser
(reading "label") saw nothing and dropped every bucket. The fix was NOT to
change the normalizer (other code already depends on its current behavior —
see test_adjudicate.py) but to declare the canonical key ("name") in the
schema/prompt from the start, so there is nothing left to rename.
"""
from __future__ import annotations

from aryx.andie_planner.schema import DASHBOARD_SPEC_SCHEMA
from aryx.llm_normalize import normalize


def test_a_literal_label_key_is_silently_renamed_to_name() -> None:
    """Documents the landmine: never declare a schema field called "label"
    (or reintroduce one for named_buckets) without reading this first."""
    raw = {"kpis": [], "business_questions": [],
          "buckets": [{"label": "Low (<=60d)", "max": 60}]}
    normalized = normalize(raw, {"type": "object", "properties": {
        "buckets": {"type": "array", "items": {"type": "object",
                                                "properties": {"label": {"type": "string"}}}}}})
    assert "label" not in normalized["buckets"][0]
    assert normalized["buckets"][0]["name"] == "Low (<=60d)"


def test_named_buckets_schema_asks_for_name_not_label() -> None:
    """The actual fix: named_buckets' bucket items are declared with "name"
    in the real schema, so there is no "label" key for the renamer to eat."""
    kpi_props = DASHBOARD_SPEC_SCHEMA["properties"]["kpis"]["items"]["properties"]
    bucket_item_props = kpi_props["buckets"]["items"]["properties"]
    assert "name" in bucket_item_props
    assert "label" not in bucket_item_props


def test_a_name_key_survives_normalization_unchanged() -> None:
    raw = {"buckets": [{"name": "Low (<=60d)", "max": 60}]}
    normalized = normalize(raw, {"type": "object", "properties": {
        "buckets": {"type": "array", "items": {"type": "object",
                                                "properties": {"name": {"type": "string"}}}}}})
    assert normalized["buckets"][0]["name"] == "Low (<=60d)"
