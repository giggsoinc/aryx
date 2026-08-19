"""Versioned planner prompt (C08) — built ONLY from approved resources.

The prompt embeds the planning_context's approved columns, graph paths, and
catalogues — never raw dataset rows, never the LLM's own invented vocabulary.
This is step 1 of the Procedure; grounding is re-verified in code afterward
(ground.py) regardless of what the prompt asked for.
"""
from __future__ import annotations

import json

PROMPT_VERSION = "1.11"

# Discipline adapted from Raven's andie-jr skill (.claude/skills/andie-jr/SKILL.md).
# andie-jr is a brownfield BUG-triage skill — its roles, verdict shape, audit
# log, and commit-message conventions do not apply to drafting a spec, so none
# of that is copied. What DOES transfer is the underlying discipline: extract
# only the minimum facts given (no broad invention), a binary grounded?
# yes/no self-check per item, no fluff, always state the rationale, and state
# uncertainty explicitly rather than guessing — the same posture andie-jr
# applies to root-causing a bug, applied here to drafting a spec.
#
# Step 3a's "layers, not a single guess" framing is adapted from Andie's Deep
# mode (.claude/skills/andie/modes/deep.md — core concept -> mental model ->
# what breaks -> next level down): drafting a spec in one flat pass is how a
# KPI's edge cases (small samples, missing values) get skipped. Only the
# *shape* of that discipline transfers — Deep mode's teaching tone/analogies
# don't apply here, this still replies with ONLY the JSON object.
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
    "2a. EVERY filter (KpiFilter, on a KPI, a numerator, or a denominator) "
    "MUST include a real 'value' or 'values' — a filter with only a column "
    "name, or filter/numerator/denominator left as null when the KPI's own "
    "name or objective implies one (e.g. a KPI named 'Active X Count' or "
    "'Renewal Rate' with no status filter counts EVERYTHING, not the subset "
    "the name promises — this is rejected outright, it is not optional just "
    "because the JSON key has a '?'). Some approved_columns entries carry "
    "'sample_values': real example values seen in that column. When a column "
    "you're filtering on has sample_values, your filter value MUST be copied "
    "verbatim from that list — never a paraphrase, a different case, a "
    "guessed synonym, or null. Worked example — a column 'status' with "
    "sample_values [\"ACTIVE\", \"DRAFT\", \"EXPIRED\"] filtered for active "
    "rows: {\"column\": \"status\", \"operator\": \"equals\", \"value\": "
    "\"ACTIVE\"} — value is NEVER left out when sample_values are available. "
    "If the column you need to filter on has NO sample_values, do not invent "
    "a plausible-looking value: leave that KPI/analysis out and record a "
    "warning instead.\n"
    "3. If the objective needs something the approved resources don't "
    "support, say so plainly in 'warnings' rather than guessing or padding.\n"
    "3a. Draft in layers, not a single flat guess: first the core, most "
    "obvious KPIs the objective needs, then one layer deeper — breakdowns, "
    "trends over time, and edge cases (small samples, missing values) the "
    "approved data can actually support. Record that layered reasoning in "
    "'assumptions', not as extra prose.\n"
    "4. For every non-obvious choice, add a one-line entry to 'assumptions' "
    "explaining why — a plan without a stated rationale is incomplete.\n"
    "5. Reply with ONLY the JSON object matching the requested shape — no "
    "preamble, no explanation outside the JSON, no markdown fences.\n\n"
    "Chart type guide — pick the type that matches the DATA SHAPE, not just "
    "habit. Never default to bar/table when a more specific type below fits "
    "the data shape better:\n"
    "- One number -> kpi_card.\n"
    "- One category, one metric -> bar (or donut for share-of-whole, <= 6 "
    "categories).\n"
    "- A trend over time (date/time group_by) -> line, area (cumulative or "
    "volume), or step (level changes).\n"
    "- Two numeric columns per row -> scatter (analysis operation "
    "row_points with x_column/y_column). Add a third numeric column -> "
    "bubble (row_points plus size_column).\n"
    "- Distribution of one numeric column -> histogram (analysis operation "
    "histogram, metric points at the KPI whose measure is the numeric "
    "column). Distribution per category -> box_plot (operation quartiles).\n"
    "- Two categorical dimensions crossed -> analysis operation crosstab "
    "(group_by = exactly those two columns), rendered as heatmap_matrix "
    "(magnitude), sankey (flow from the first column to the second), or "
    "treemap/sunburst (part-of-whole hierarchy).\n"
    "- Before/after or a two-point comparison per category -> slopegraph; a "
    "full second series per category -> grouped_bar (needs compare_ref).\n"
    "- Ordered contributions to a total (gains/losses) -> waterfall. Ranked "
    "contribution plus cumulative share -> pareto.\n"
    "- Start/end dates per item -> gantt (analysis operation date_span with "
    "start_column/end_column).\n"
    "- Time-to-event or retention over time -> survival_curve (analysis "
    "operation survival with start_column, and end_column only for rows "
    "that actually exited/churned).\n"
    "- Several metrics compared for one entity/segment -> radar (needs "
    "visualizations.axis_refs with 3 or more kpi_id/analysis_id refs).\n"
    "- A relationship from the knowledge graph itself (not a flat column) -> "
    "analysis operation graph_relation: set graph_path_id to one of the "
    "approved_graph_paths ids (never invent one), leave group_by and metric "
    "empty. Only cite a path you believe is a single, direct hop between two "
    "entity types — deeper multi-hop paths are not supported yet and will "
    "simply fail to render. Visualize a graph_relation analysis as bar or "
    "donut only (it produces one count per related entity, not a 2D shape) — "
    "never sankey/treemap/heatmap_matrix for this operation. If "
    "graph_path_hints is present, use its 'label' (e.g. 'Customer -> "
    "CONTRACT_CUSTOMER -> Contract') and 'depth' (cite depth 1 only) to judge "
    "which path_id is actually relevant to the objective — never cite a "
    "path_id that has no matching graph_path_hints entry. If "
    "graph_quality_notes is present, ground any relevant 'assumptions' entry "
    "in it (e.g. a known data-quality gap) rather than guessing at caveats."
)


def build_planner_prompt(
    *,
    approved_columns: list[dict[str, object]],
    approved_graph_paths: list[str],
    supported_operations: list[str],
    supported_charts: list[str],
    objective: str,
    target_audience: str,
    output_schema_version: str,
    domain: str = "",
    brief_context: str = "",
    user_preferences: dict[str, object] | None = None,
    graph_path_hints: list[dict[str, object]] | None = None,
    graph_quality_notes: list[str] | None = None,
) -> tuple[str, str]:
    """Build the (system, user) prompt pair from approved resources only.

    Args:
        approved_columns: [{"name": ..., "type": ..., "sample_values": [...]},
            ...] from the C07 planning context — the only columns the model
            may reference. sample_values are real observed values (may be
            empty for non-categorical/high-cardinality columns).
        approved_graph_paths: verified graph path ids (C06) available to cite.
        supported_operations / supported_charts: the approved catalogues.
        brief_context: the rest of the customer brief (scope, objectives,
            proof questions, audiences) as prose. Steers the plan but is
            NEVER written onto the spec — `objective` stays the short,
            human-readable line the dashboard is titled with.
        user_preferences: C01 IntentPreferences fields (preferred_kpis,
            preferred_dimensions, preferred_chart_types, date_range) — hints,
            never a substitute for the approved-resources restriction.
        graph_path_hints: [{"path_id", "label", "depth"}, ...] — readable
            rendering of each approved_graph_paths entry, so the model can
            judge relevance instead of picking blind among bare ids.
        graph_quality_notes: readable C06 quality flags/limitations to ground
            'assumptions' in real data-quality caveats, not guesses.
    """
    resources = {
        "approved_columns": approved_columns,
        "approved_graph_paths": approved_graph_paths,
        "supported_operations": supported_operations,
        "supported_charts": supported_charts,
    }
    if user_preferences:
        resources["user_preferences"] = user_preferences
    if graph_path_hints:
        resources["graph_path_hints"] = graph_path_hints
    if graph_quality_notes:
        resources["graph_quality_notes"] = graph_quality_notes
    user = (
        f"Domain: {domain or 'general'}\n"
        f"Objective: {objective}\n"
        + (f"\nCustomer brief — plan against ALL of this:\n{brief_context}\n\n"
           if brief_context.strip() else "")
        + f"Target audience: {target_audience or 'general business audience'}\n"
        f"Output schema version: {output_schema_version}\n\n"
        "Approved resources (the ONLY vocabulary you may use):\n"
        f"{json.dumps(resources, indent=2)}\n\n"
        "Cover a real SPREAD of the objective: propose at least 10 and no "
        "more than 12 visualizations total — a single KPI card is not a "
        "dashboard. business_questions is a 3-5 item summary of the "
        "objective, not a checklist visualizations must map onto — draft "
        "every KPI, analysis, and visualization from the approved resources "
        "and the objective directly; a visualization does not need to trace "
        "back to any one business_question. Every visualization must "
        "surface information no other visualization already shows (a "
        "different column, grouping, metric, or graph relationship) — never "
        "pad the count with two charts of the same group_by/metric wearing "
        "different chart_types. If user_preferences is present, treat "
        "preferred_kpis/preferred_dimensions/preferred_chart_types as strong "
        "hints to prioritize when the approved resources support them (never "
        "an excuse to use an unapproved column/chart type), and date_range "
        "as a hint for which date-grouped analyses matter most, not a row "
        "filter. If any approved_columns entry looks like a date/time "
        "column, include at least one analysis grouped by it (e.g. by month "
        "or period) so a trend over time is visible, rendered with "
        "whichever supported_charts type fits.\n\n"
        "Return a JSON object with exactly these keys:\n"
        "business_questions: [{question_id, text}] — propose 3 to 5.\n"
        "kpis: [{kpi_id, name, source_columns, operation, measure?, filter?, "
        "numerator?, denominator?, zero_denominator_policy?, format}] — "
        "operation and any nested operation must be one of "
        "supported_operations; source_columns/measure/filter.column must be "
        "approved_columns names. zero_denominator_policy is REQUIRED for "
        "ratio/percentage KPIs and its value MUST be exactly the string "
        "'return_null_with_warning' — it is the only value implemented; any "
        "other value (e.g. 'return_zero', 'skip') is rejected.\n"
        "analyses: [{analysis_id, operation, group_by, metric?, sort?, "
        "x_column?, y_column?, size_column?, start_column?, end_column?, "
        "graph_path_id?}] — group_by columns must be approved_columns "
        "names; metric must be a kpi_id you defined above; operation must "
        "be one of supported_operations. x_column/y_column/size_column are "
        "for row_points (scatter/bubble) only; start_column/end_column are "
        "for date_span (gantt) or survival only — all five must be "
        "approved_columns names when used. graph_path_id is for "
        "graph_relation only — one of approved_graph_paths, and group_by/"
        "metric must be left empty for that operation.\n"
        "visualizations: [{chart_id, chart_type, source_ref, x_axis?, "
        "y_axis?, compare_ref?, axis_refs?}] — chart_type must be one of "
        "supported_charts; source_ref must be a kpi_id or analysis_id you "
        "defined above; compare_ref is for grouped_bar/slopegraph only; "
        "axis_refs is for radar only (list of 3+ kpi_id/analysis_id refs, "
        "one per axis).\n"
        "assumptions: [{code, meaning}] — any assumption you made.\n"
        "warnings: [{code, column?, detail?}] — anything you could not "
        "support with the approved resources (e.g. a missing column needed "
        "for the objective).\n\n"
        "Before replying, re-check every filter you wrote (on a kpi, a "
        "numerator, or a denominator): does its column actually have "
        "sample_values listed in approved_columns above? If that column's "
        "sample_values is empty or missing, DROP that whole kpi/analysis and "
        "record a warning instead — do not keep a filter with no value, and "
        "do not invent one. This exact mistake is the most common reason a "
        "draft gets rejected."
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
    brief_context: str = "",
    user_preferences: dict[str, object] | None = None,
    graph_path_hints: list[dict[str, object]] | None = None,
    graph_quality_notes: list[str] | None = None,
) -> tuple[str, str]:
    """Build the (system, user) prompt pair spanning EVERY dataset in a workspace.

    Args:
        datasets: [{"dataset_id": ..., "approved_columns": [{"name","type"},...]},
            ...] — grouped per dataset, never flattened (see ground.py's
            docstring for why: column names collide across unrelated
            datasets often enough that a flat list would be ambiguous).
        user_preferences: C01 IntentPreferences fields — see
            build_planner_prompt for the same meaning/hint-only treatment.
        graph_path_hints / graph_quality_notes: see build_planner_prompt —
            same meaning, workspace-wide instead of per-dataset.
    """
    resources = {
        "datasets": datasets,
        "approved_graph_paths": approved_graph_paths,
        "supported_operations": supported_operations,
        "supported_charts": supported_charts,
    }
    if user_preferences:
        resources["user_preferences"] = user_preferences
    if graph_path_hints:
        resources["graph_path_hints"] = graph_path_hints
    if graph_quality_notes:
        resources["graph_quality_notes"] = graph_quality_notes
    user = (
        f"Domain: {domain or 'general'}\n"
        f"Objective: {objective}\n"
        + (f"\nCustomer brief — plan against ALL of this:\n{brief_context}\n\n"
           if brief_context.strip() else "")
        + f"Target audience: {target_audience or 'general business audience'}\n"
        f"Output schema version: {output_schema_version}\n\n"
        "This workspace has MULTIPLE datasets. Approved resources are grouped "
        "per dataset below — the SAME column name can mean different things "
        "in different datasets, so every KPI and analysis you propose MUST "
        "declare exactly which dataset its columns come from:\n"
        f"{json.dumps(resources, indent=2)}\n\n"
        "Cover a real SPREAD of the objective: propose at least 10 and no "
        "more than 12 visualizations total across the whole workspace — a "
        "single KPI card is not a dashboard. business_questions is a 3-5 "
        "item summary of the objective, not a checklist visualizations must "
        "map onto — draft every KPI, analysis, and visualization from the "
        "approved resources and the objective directly; a visualization "
        "does not need to trace back to any one business_question. Every "
        "visualization must surface information no other visualization "
        "already shows (a different column, grouping, metric, or graph "
        "relationship) — never pad the count with two charts of the same "
        "group_by/metric wearing different chart_types. If "
        "user_preferences is present, treat preferred_kpis/"
        "preferred_dimensions/preferred_chart_types as strong hints to "
        "prioritize when the approved resources support them (never an "
        "excuse to use an unapproved column/chart type), and date_range as "
        "a hint for which date-grouped analyses matter most, not a row "
        "filter. If any dataset's approved_columns has a "
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
        "dataset's own list, never another dataset's. "
        "zero_denominator_policy is REQUIRED for ratio/percentage KPIs and "
        "its value MUST be exactly the string 'return_null_with_warning' — "
        "it is the only value implemented; any other value is rejected.\n"
        "analyses: [{analysis_id, operation, dataset_id, group_by, metric?, "
        "sort?, x_column?, y_column?, size_column?, start_column?, "
        "end_column?, graph_path_id?}] — dataset_id likewise required "
        "(leave empty for graph_relation, which spans the whole workspace "
        "graph, not one dataset); group_by columns must belong to that "
        "dataset; metric must be a kpi_id you defined above; operation must "
        "be one of supported_operations. x_column/y_column/size_column are "
        "for row_points (scatter/bubble) only; start_column/end_column are "
        "for date_span (gantt) or survival only — all five must belong to "
        "that same dataset. graph_path_id is for graph_relation only — one "
        "of approved_graph_paths, with group_by/metric left empty.\n"
        "visualizations: [{chart_id, chart_type, source_ref, x_axis?, "
        "y_axis?, compare_ref?, axis_refs?}] — chart_type must be one of "
        "supported_charts; source_ref must be a kpi_id or analysis_id you "
        "defined above (visualizations do not need their own dataset_id — "
        "it's implied by source_ref); compare_ref is for grouped_bar/"
        "slopegraph only; axis_refs is for radar only (3+ refs, one per "
        "axis, which may span different datasets).\n"
        "assumptions: [{code, meaning}] — any assumption you made, including "
        "how datasets relate via approved_graph_paths if relevant.\n"
        "warnings: [{code, column?, detail?}] — anything you could not "
        "support with the approved resources.\n\n"
        "Before replying, re-check every kpi/analysis you drafted: does its "
        "dataset_id EXACTLY match one of the dataset_id values in 'datasets' "
        "above, and does every column it cites actually appear in THAT SAME "
        "dataset's own approved_columns list (not a different dataset's, even "
        "if the name looks the same)? A single wrong pairing here fails the "
        "whole spec — fix or drop the item now rather than risk it. Also "
        "re-check every filter (on a kpi, a numerator, or a denominator): "
        "does its column actually have sample_values listed under that "
        "dataset's approved_columns? If that column's sample_values is empty "
        "or missing, DROP that whole kpi/analysis and record a warning "
        "instead — do not keep a filter with no value. This exact mistake is "
        "the most common reason a draft gets rejected."
    )
    return _SYSTEM, user


def build_delta_prompt(
    *,
    existing_kpis: list[dict[str, object]],
    existing_analyses: list[dict[str, object]],
    approved_columns: list[dict[str, object]] | None = None,
    datasets: list[dict[str, object]] | None = None,
    approved_graph_paths: list[str],
    supported_operations: list[str],
    supported_charts: list[str],
    request_text: str,
    domain: str = "",
    graph_path_hints: list[dict[str, object]] | None = None,
    graph_quality_notes: list[str] | None = None,
) -> tuple[str, str]:
    """Build the (system, user) prompt pair for ONE ask-to-visualize request —
    extends an already-approved spec rather than drafting a whole one.

    Reuses `_SYSTEM` unchanged: the "no invention" discipline and chart-type
    guide are exactly as applicable to one chart as to a whole dashboard: only
    the `user` message differs (existing spec as context, one request instead
    of an objective, a narrower required shape).

    Single-dataset vs. workspace-scope mirrors `build_planner_prompt` /
    `build_workspace_planner_prompt`'s split: pass `approved_columns` for a
    single dataset, or `datasets` (grouped per dataset, like
    `build_workspace_planner_prompt`) for a workspace-scope spec — exactly
    one of the two, never both.

    Args:
        existing_kpis / existing_analyses: [{"kpi_id"/"analysis_id", "name"?,
            "operation", "group_by"?, "metric"?}, ...] — the current spec's own
            items, so the model can point a new Visualization at one of these
            via source_ref instead of redrafting it.
        request_text: the customer's own words — never executed, only grounded.
    """
    workspace_mode = datasets is not None
    resources: dict[str, object] = {
        "existing_kpis": existing_kpis,
        "existing_analyses": existing_analyses,
        "approved_graph_paths": approved_graph_paths,
        "supported_operations": supported_operations,
        "supported_charts": supported_charts,
    }
    if workspace_mode:
        resources["datasets"] = datasets
    else:
        resources["approved_columns"] = approved_columns or []
    if graph_path_hints:
        resources["graph_path_hints"] = graph_path_hints
    if graph_quality_notes:
        resources["graph_quality_notes"] = graph_quality_notes

    dataset_id_note = (
        " This workspace has MULTIPLE datasets, grouped under 'datasets' below — "
        "a new_kpi/new_analysis you draft MUST declare its own dataset_id (except "
        "graph_relation, which spans the whole workspace graph and leaves "
        "dataset_id empty), and its columns must come from THAT SAME dataset's "
        "own approved_columns list."
        if workspace_mode else ""
    )
    user = (
        f"Domain: {domain or 'general'}\n\n"
        "You are EXTENDING an already-approved dashboard, not replacing it. "
        "The dashboard already has the KPIs and analyses listed under "
        "'existing_kpis'/'existing_analyses' below — if the customer's request "
        "can be answered by charting one of THOSE as-is, do that (point "
        "new_visualization.source_ref at its existing kpi_id/analysis_id) "
        "rather than drafting a new one. Only draft a new KPI or analysis if "
        "the request genuinely needs a column/grouping/measure combination "
        "that doesn't already exist. At most ONE new KPI, at most ONE new "
        f"analysis, EXACTLY one new visualization.{dataset_id_note}\n\n"
        "Approved resources (the ONLY vocabulary you may use):\n"
        f"{json.dumps(resources, indent=2)}\n\n"
        f"Customer request: {request_text}\n\n"
        "Return a JSON object with exactly these keys:\n"
        "new_kpi: {kpi_id, name, " + ("dataset_id, " if workspace_mode else "") +
        "source_columns, operation, measure?, filter?, numerator?, denominator?, "
        "zero_denominator_policy?, format} or null — omit/null when reusing an "
        "existing KPI. Same field rules as the full planner (operation must be "
        "one of supported_operations; source_columns/measure/filter.column must "
        "be approved_columns names; filter values must be copied verbatim from "
        "that column's sample_values, per the discipline above). "
        "zero_denominator_policy is REQUIRED for ratio/percentage operation and "
        "its value MUST be exactly the string 'return_null_with_warning' — it "
        "is the only value implemented; any other value is rejected.\n"
        "new_analysis: {analysis_id, operation, " + ("dataset_id, " if workspace_mode else "") +
        "group_by, metric?, sort?, x_column?, y_column?, size_column?, "
        "start_column?, end_column?, graph_path_id?} or null — omit/null when "
        "reusing an existing analysis. metric may cite new_kpi's kpi_id if "
        "you drafted one, or an existing kpi_id. graph_path_id is for "
        "operation graph_relation only — one of approved_graph_paths (see "
        "graph_path_hints if present), with group_by/metric left empty"
        + (" and dataset_id left empty (it spans the whole workspace graph, "
           "not one dataset)" if workspace_mode else "") + ".\n"
        "new_visualization: {chart_id, chart_type, source_ref, x_axis?, "
        "y_axis?, compare_ref?, axis_refs?} — the goal of this request. "
        "chart_type must be one of supported_charts; source_ref must be "
        "new_analysis's/new_kpi's own id if you drafted one, or an existing "
        "kpi_id/analysis_id (visualizations never need their own dataset_id — "
        "it's implied by source_ref). Omit only if truly unsupportable (see "
        "warnings).\n"
        "warnings: [{code, column?, detail?}] — if the request cannot be "
        "supported by the approved resources at all, say so here instead of "
        "guessing, and omit new_visualization.\n\n"
        "Before replying, if new_kpi or new_analysis has any filter (on the "
        "kpi, a numerator, or a denominator), re-check that its column "
        "actually has sample_values listed in the approved resources above. "
        "If that column's sample_values is empty or missing, drop the filter "
        "by dropping the whole new_kpi/new_analysis and warn instead — do "
        "not keep a filter with no value."
    )
    return _SYSTEM, user


def build_filter_repair_prompt(*, items: list[dict[str, object]], objective: str) -> tuple[str, str]:
    """Targeted micro-repair for missing_filter_value (see filter_repair.py).

    Deliberately NOT a redraft: the model is fixing specific, already-known
    defects (a filter with a real column but no value), not drafting
    anything new. Each item already carries that column's REAL sample_values
    — the only ones a returned value may ever match.

    Args:
        items: [{"kpi_id", "field", "kpi_name", "column", "sample_values"}, ...]
            — one per broken filter (see filter_repair._broken_filter_refs).
    """
    system = (
        "You are fixing a specific, already-identified defect in an "
        "existing dashboard KPI list — you are NOT drafting anything new. "
        "Each item below names one KPI whose filter is missing a value; the "
        "column and its REAL observed sample_values are given.\n\n"
        "For each item:\n"
        "1. If the KPI's own name clearly implies filtering on one of the "
        "listed sample_values (e.g. a KPI named 'Active X Count' on a "
        "column whose sample_values include 'ACTIVE'), reply with that "
        "EXACT string, copied verbatim — never a different case, never a "
        "paraphrase, never a value not in the list.\n"
        "2. If no sample_value clearly applies, or you are not confident, "
        "reply null for that item — never guess.\n"
        "3. Reply with ONLY the JSON object — no preamble, no explanation."
    )
    user = (
        f"Dashboard objective: {objective}\n\n"
        "Broken filters to resolve:\n"
        f"{json.dumps(items, indent=2)}\n\n"
        "Return a JSON object with exactly this key:\n"
        "fills: [{kpi_id, field, value}] — one entry per item above, in the "
        "same order; value is a string copied verbatim from that item's own "
        "sample_values, or null if none applies."
    )
    return system, user


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
    (pre-execution validation) rejected for specific, itemized reasons.

    Framed as one Kaizen Cycle (Andie's modes/kaizen.md default method: one
    fix, verify, iterate) — not a re-guess from scratch. `constraints_text`
    (built by spec_validation.validate.repair_constraints_text) already names
    the exact real defect per error; this framing only changes HOW that's
    presented, never what it says.
    """
    kaizen_frame = (
        "Your previous draft was REJECTED by validation. Treat this as one "
        "repair cycle, not a re-guess from scratch:\n"
        "- Problem pattern: the exact errors below — these are real, not "
        "hypothetical.\n"
        "- Root cause: each error names the actual defect; do not guess at "
        "a different one.\n"
        "- Fix: change ONLY what each error names. Keep every KPI, analysis, "
        "and visualization that was NOT flagged exactly as it was.\n\n"
    )
    return f"{user}\n\n{kaizen_frame}{constraints_text}"
