"""Versioned planner prompt (C08) — built ONLY from approved resources.

The prompt embeds the planning_context's approved columns, graph paths, and
catalogues — never raw dataset rows, never the LLM's own invented vocabulary.
This is step 1 of the Procedure; grounding is re-verified in code afterward
(ground.py) regardless of what the prompt asked for.
"""
from __future__ import annotations

import json

PROMPT_VERSION = "1.2"

# Discipline adapted from Raven's andie-jr skill (.claude/skills/andie-jr/SKILL.md).
# andie-jr is a brownfield BUG-triage skill — its roles, verdict shape, audit
# log, and commit-message conventions do not apply to drafting a spec, so none
# of that is copied. What DOES transfer is the underlying discipline: extract
# only the minimum facts given (no broad invention), a binary grounded?
# yes/no self-check per item, no fluff, always state the rationale, and state
# uncertainty explicitly rather than guessing — the same posture andie-jr
# applies to root-causing a bug, applied here to drafting a spec.
_SYSTEM = (
    "You are a dashboard planning assistant. You draft a CANDIDATE, "
    "NON-EXECUTABLE dashboard specification — business questions, KPI "
    "definitions, analyses, and chart requests. "
    "You must NEVER compute or state an actual KPI value or percentage. "
    "You must NEVER make a causal or explanatory claim about WHY a number is "
    "what it is (e.g. blaming a region or a team) — only propose what to ask "
    "and how to visualize it. "
    "You may ONLY reference column names, operations, and chart types from "
    "the 'approved resources' list below — never invent a column, operation, "
    "or chart type that is not listed. If no approved resource supports part "
    "of the objective, say so in a warning instead of inventing one.\n\n"
    "Discipline:\n"
    "1. Use ONLY the approved resources given below — do not add, assume, or "
    "infer any column, path, operation, or chart type beyond what is listed, "
    "even if something else seems obviously useful.\n"
    "2. Before including any KPI, analysis, or visualization, check: is every "
    "column, operation, and chart type it uses explicitly present in the "
    "approved resources? If no for any part, leave that item out entirely and "
    "record a warning instead — never approximate with something similar.\n"
    "3. If the objective needs something the approved resources don't "
    "support, say so plainly in 'warnings' rather than guessing or padding.\n"
    "4. For every non-obvious choice, add a one-line entry to 'assumptions' "
    "explaining why — a plan without a stated rationale is incomplete.\n"
    "5. Reply with ONLY the JSON object matching the requested shape — no "
    "preamble, no explanation outside the JSON, no markdown fences."
)


def build_planner_prompt(
    *,
    approved_columns: list[dict[str, str]],
    approved_graph_paths: list[str],
    supported_operations: list[str],
    supported_charts: list[str],
    objective: str,
    target_audience: str,
    output_schema_version: str,
    domain: str = "",
) -> tuple[str, str]:
    """Build the (system, user) prompt pair from approved resources only.

    Args:
        approved_columns: [{"name": ..., "type": ...}, ...] from the C07
            planning context — the only columns the model may reference.
        approved_graph_paths: verified graph path ids (C06) available to cite.
        supported_operations / supported_charts: the approved catalogues.
    """
    resources = {
        "approved_columns": approved_columns,
        "approved_graph_paths": approved_graph_paths,
        "supported_operations": supported_operations,
        "supported_charts": supported_charts,
    }
    user = (
        f"Domain: {domain or 'general'}\n"
        f"Objective: {objective}\n"
        f"Target audience: {target_audience or 'general business audience'}\n"
        f"Output schema version: {output_schema_version}\n\n"
        "Approved resources (the ONLY vocabulary you may use):\n"
        f"{json.dumps(resources, indent=2)}\n\n"
        "Cover a real SPREAD of the objective: propose at least 4 and no more "
        "than 6 visualizations total — a single KPI card is not a dashboard. "
        "If any approved_columns entry looks like a date/time column, include "
        "at least one analysis grouped by it (e.g. by month or period) so a "
        "trend over time is visible, rendered with whichever supported_charts "
        "type fits.\n\n"
        "Return a JSON object with exactly these keys:\n"
        "business_questions: [{question_id, text}] — propose 3 to 5.\n"
        "kpis: [{kpi_id, name, source_columns, operation, measure?, filter?, "
        "numerator?, denominator?, zero_denominator_policy?, format}] — "
        "operation and any nested operation must be one of "
        "supported_operations; source_columns/measure/filter.column must be "
        "approved_columns names.\n"
        "analyses: [{analysis_id, operation, group_by, metric?, sort?}] — "
        "group_by columns must be approved_columns names; metric must be a "
        "kpi_id you defined above; operation must be one of "
        "supported_operations.\n"
        "visualizations: [{chart_id, chart_type, source_ref, x_axis?, "
        "y_axis?}] — chart_type must be one of supported_charts; source_ref "
        "must be a kpi_id or analysis_id you defined above.\n"
        "assumptions: [{code, meaning}] — any assumption you made.\n"
        "warnings: [{code, column?, detail?}] — anything you could not "
        "support with the approved resources (e.g. a missing column needed "
        "for the objective)."
    )
    return _SYSTEM, user


def build_workspace_planner_prompt(
    *,
    datasets: list[dict[str, object]],
    approved_graph_paths: list[str],
    supported_operations: list[str],
    supported_charts: list[str],
    objective: str,
    target_audience: str,
    output_schema_version: str,
    domain: str = "",
) -> tuple[str, str]:
    """Build the (system, user) prompt pair spanning EVERY dataset in a workspace.

    Args:
        datasets: [{"dataset_id": ..., "approved_columns": [{"name","type"},...]},
            ...] — grouped per dataset, never flattened (see ground.py's
            docstring for why: column names collide across unrelated
            datasets often enough that a flat list would be ambiguous).
    """
    resources = {
        "datasets": datasets,
        "approved_graph_paths": approved_graph_paths,
        "supported_operations": supported_operations,
        "supported_charts": supported_charts,
    }
    user = (
        f"Domain: {domain or 'general'}\n"
        f"Objective: {objective}\n"
        f"Target audience: {target_audience or 'general business audience'}\n"
        f"Output schema version: {output_schema_version}\n\n"
        "This workspace has MULTIPLE datasets. Approved resources are grouped "
        "per dataset below — the SAME column name can mean different things "
        "in different datasets, so every KPI and analysis you propose MUST "
        "declare exactly which dataset its columns come from:\n"
        f"{json.dumps(resources, indent=2)}\n\n"
        "Cover a real SPREAD of the objective: propose at least 4 and no more "
        "than 6 visualizations total across the whole workspace — a single "
        "KPI card is not a dashboard. If any dataset's approved_columns has a "
        "date/time column, include at least one analysis grouped by it (e.g. "
        "by month or period) so a trend over time is visible, rendered with "
        "whichever supported_charts type fits.\n\n"
        "Return a JSON object with exactly these keys:\n"
        "business_questions: [{question_id, text}] — propose 3 to 5, "
        "spanning multiple datasets where useful.\n"
        "kpis: [{kpi_id, name, dataset_id, source_columns, operation, "
        "measure?, filter?, numerator?, denominator?, "
        "zero_denominator_policy?, format}] — dataset_id MUST be one of the "
        "dataset_id values listed in 'datasets' above; source_columns/measure/"
        "filter.column must be approved_columns names from THAT SAME "
        "dataset's own list, never another dataset's.\n"
        "analyses: [{analysis_id, operation, dataset_id, group_by, metric?, "
        "sort?}] — dataset_id likewise required; group_by columns must "
        "belong to that dataset; metric must be a kpi_id you defined above; "
        "operation must be one of supported_operations.\n"
        "visualizations: [{chart_id, chart_type, source_ref, x_axis?, "
        "y_axis?}] — chart_type must be one of supported_charts; source_ref "
        "must be a kpi_id or analysis_id you defined above (visualizations "
        "do not need their own dataset_id — it's implied by source_ref).\n"
        "assumptions: [{code, meaning}] — any assumption you made, including "
        "how datasets relate via approved_graph_paths if relevant.\n"
        "warnings: [{code, column?, detail?}] — anything you could not "
        "support with the approved resources."
    )
    return _SYSTEM, user


def repair_prompt(user: str, reason: str) -> str:
    """Append a repair reminder after a malformed/empty first attempt."""
    return (
        f"{user}\n\n"
        f"Your previous response was rejected ({reason}). "
        "Return ONLY the JSON object with the exact keys requested — "
        "business_questions, kpis, analyses, visualizations, assumptions, "
        "warnings — no other text."
    )


def append_repair_constraints(user: str, constraints_text: str) -> str:
    """Append C09's structured correction constraints for the one allowed
    validation-repair retry. Distinct from `repair_prompt`: that one handles a
    malformed/empty LLM response; this handles a well-formed spec that C09
    (pre-execution validation) rejected for specific, itemized reasons."""
    return f"{user}\n\n{constraints_text}"
