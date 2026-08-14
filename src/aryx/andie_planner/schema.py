"""JSON schema hint for complete_json's envelope normalization (C08).

This is NOT the grounding enforcement — Ollama's format=json guarantees valid
JSON syntax but does not validate against this shape, and even providers that
do honor a schema only constrain structure, not content. `ground.py` is the
real, code-level enforcement of column/operation/chart correctness.

`operation`/`chart_type`/`zero_denominator_policy` are enum-restricted to the
real catalogues (planning.catalogues) below — column/dataset_id/graph_path_id
stay free-text because their valid set is per-dataset/per-workspace, not a
static catalogue a shared schema can enumerate. NOTE: as of this writing,
`aryx.llm_providers.openai_json` (Groq/Gemini) sends `response_format:
{"type": "json_object"}`, not `json_schema` — so these enums are not yet
transmitted as provider-side enforcement, only used for complete_json's own
envelope normalization. ground.py/checks.py remain the real enforcement
either way.
"""
from __future__ import annotations

from aryx.planning.catalogues import CHARTS, OPERATIONS

_RATIO_OPERAND_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["count"]},
        "filter": {"type": "object"},
    },
}
_ZERO_DENOMINATOR_POLICY_SCHEMA: dict = {"type": "string", "enum": ["return_null_with_warning"]}

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
                    "operation": {"type": "string", "enum": OPERATIONS},
                    "measure": {"type": "string"},
                    "filter": {"type": "object"},
                    "numerator": _RATIO_OPERAND_SCHEMA,
                    "denominator": _RATIO_OPERAND_SCHEMA,
                    "zero_denominator_policy": _ZERO_DENOMINATOR_POLICY_SCHEMA,
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
                    "operation": {"type": "string", "enum": OPERATIONS},
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
                    "chart_type": {"type": "string", "enum": CHARTS},
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

# One ask-to-visualize request (see andie_planner.delta) — a narrower shape
# than DASHBOARD_SPEC_SCHEMA: at most one new KPI/analysis, exactly one
# visualization, extending an already-approved spec rather than replacing it.
DELTA_SPEC_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "new_kpi": {
            "type": "object",
            "properties": {
                "kpi_id": {"type": "string"},
                "name": {"type": "string"},
                "source_columns": {"type": "array", "items": {"type": "string"}},
                "operation": {"type": "string", "enum": OPERATIONS},
                "measure": {"type": "string"},
                "filter": {"type": "object"},
                "numerator": _RATIO_OPERAND_SCHEMA,
                "denominator": _RATIO_OPERAND_SCHEMA,
                "zero_denominator_policy": _ZERO_DENOMINATOR_POLICY_SCHEMA,
                "format": {"type": "string"},
            },
        },
        "new_analysis": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "string"},
                "operation": {"type": "string", "enum": OPERATIONS},
                "group_by": {"type": "array", "items": {"type": "string"}},
                "metric": {"type": "string"},
                "sort": {"type": "string"},
                "x_column": {"type": "string"},
                "y_column": {"type": "string"},
                "size_column": {"type": "string"},
                "start_column": {"type": "string"},
                "end_column": {"type": "string"},
            },
        },
        "new_visualization": {
            "type": "object",
            "properties": {
                "chart_id": {"type": "string"},
                "chart_type": {"type": "string", "enum": CHARTS},
                "source_ref": {"type": "string"},
                "x_axis": {"type": "string"},
                "y_axis": {"type": "string"},
                "compare_ref": {"type": "string"},
                "axis_refs": {"type": "array", "items": {"type": "string"}},
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
    "required": [],
    "additionalProperties": False,
}

# Targeted micro-repair for missing_filter_value (see filter_repair.py) — a
# much narrower shape than DASHBOARD_SPEC_SCHEMA: fix specific broken
# filters using their column's REAL sample_values, never redraft anything.
FILTER_REPAIR_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "fills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kpi_id": {"type": "string"},
                    "field": {"type": "string"},
                    "value": {"type": ["string", "null"]},
                },
                "required": ["kpi_id", "field"],
            },
        },
    },
    "required": ["fills"],
    "additionalProperties": False,
}
