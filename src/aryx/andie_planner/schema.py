"""JSON schema hint for complete_json's envelope normalization (C08).

This is NOT the grounding enforcement — Ollama's format=json guarantees valid
JSON syntax but does not validate against this shape, and even providers that
do honor a schema only constrain structure, not content. `ground.py` is the
real, code-level enforcement of column/operation/chart correctness.
"""
from __future__ import annotations

DASHBOARD_SPEC_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "business_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
        },
        "kpis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kpi_id": {"type": "string"},
                    "name": {"type": "string"},
                    "source_columns": {"type": "array", "items": {"type": "string"}},
                    "operation": {"type": "string"},
                    "measure": {"type": "string"},
                    "filter": {"type": "object"},
                    "numerator": {"type": "object"},
                    "denominator": {"type": "object"},
                    "zero_denominator_policy": {"type": "string"},
                    "format": {"type": "string"},
                },
                "required": ["kpi_id", "operation"],
            },
        },
        "analyses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "analysis_id": {"type": "string"},
                    "operation": {"type": "string"},
                    "group_by": {"type": "array", "items": {"type": "string"}},
                    "metric": {"type": "string"},
                    "sort": {"type": "string"},
                },
                "required": ["analysis_id", "operation"],
            },
        },
        "visualizations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chart_id": {"type": "string"},
                    "chart_type": {"type": "string"},
                    "source_ref": {"type": "string"},
                    "x_axis": {"type": "string"},
                    "y_axis": {"type": "string"},
                },
                "required": ["chart_id", "chart_type", "source_ref"],
            },
        },
        "assumptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"code": {"type": "string"}, "meaning": {"type": "string"}},
            },
        },
        "warnings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "column": {"type": "string"},
                    "detail": {"type": "string"},
                },
            },
        },
    },
    "required": ["business_questions", "kpis"],
    "additionalProperties": False,
}
