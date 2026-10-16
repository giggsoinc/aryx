"""Targeted micro-repair for missing_filter_value (C08 addendum).

Every model tried against this prompt this session (llama-3.3-70b-versatile,
gpt-oss-120b, gemini-flash-latest — even at temperature=0.1) has, at some
rate, drafted a KPI whose name implies a filter (e.g. "Active Contracts
Count") but left the filter's value empty. Grounding already drops that one
filter safely (never invents), but C09 then rejects the WHOLE spec over it,
burning the one full-spec repair retry on a defect that's actually tiny and
well-understood: one column, a short list of real sample_values, one value
to pick (or explicitly decline).

This module fixes exactly that, cheaply: instead of asking the model to
redraft the entire spec, ask it ONE narrow question per broken filter — pick
a real sample_value or say null — and patch just those KPIs. Confirmed live
the model correctly distinguishes the two cases: given "status" with
sample_values ["ACTIVE","DRAFT","EXPIRED","TERMINATED"] for a KPI named
"Active Contracts Count", it filled in "ACTIVE"; given "renewal_status" with
sample_values that don't semantically map to "renewed" at all, it correctly
declined with null rather than guess.

For anything that stays unresolved (declined, invalid answer, or no real
sample_values to even offer), the WHOLE KPI is dropped — not just its
filter. Leaving the KPI with `filter=None` would be unsafe: an operand
meant to be "count where X" silently becomes "count of everything",
producing a wrong, non-null number that would look legitimate. Dropping the
KPI is the same "no invention" fallback grounding already uses for an
unapproved column — this module just extends it to a KPI that turned out to
be unresolvable only after the narrow follow-up question was asked.
"""
from __future__ import annotations

from typing import Any, Callable

from aryx.andie_planner.models import DashboardSpec, Kpi, KpiFilter, SpecWarning
from aryx.andie_planner.prompt import build_filter_repair_prompt
from aryx.andie_planner.schema import FILTER_REPAIR_SCHEMA

CompleteJsonFn = Callable[[Any, str, str, str, dict], dict]

_FIELDS = ("filter", "numerator", "denominator")

# Same boolean-token vocabulary as the profiler's own is_bool check
# (aryx.profiler.profile._BOOL_TRUE/_BOOL_FALSE) — the two must agree on what
# counts as "boolean" or a column the profiler labels boolean could fail to
# normalize here.
_BOOL_TRUE = {"true", "yes", "y", "1", "t"}
_BOOL_FALSE = {"false", "no", "n", "0", "f"}


def _normalize_boolean_fill(value: str, samples: list[str]) -> str:
    """Map a true/false synonym the model returned onto the REAL sample
    value that means the same thing, when the column is a boolean flag.

    A derived flag column (is_renewed, is_at_risk, ...) is profiled with
    bare sample_values like ["0", "1"] — nothing in those two characters
    tells the model which one means "true". Asked to fill a filter for a
    KPI named "Overall Renewal Rate", a model reasons in true/false and
    often answers "true" even though the real data encodes that as "1": a
    correct answer in substance, rejected by a verbatim string match. This
    only fires when EVERY sample_value for the column is itself a
    recognized boolean token (so a genuine categorical column like
    status=DRAFT/ACTIVE/EXPIRED is never touched), and it only ever
    substitutes one real sample_value for another — never invents one.
    """
    samples_lower = [s.lower() for s in samples]
    if not samples or any(s not in _BOOL_TRUE | _BOOL_FALSE for s in samples_lower):
        return value
    value_lower = str(value).lower()
    if value_lower in _BOOL_TRUE:
        target = next((s for s in samples if s.lower() in _BOOL_TRUE), None)
    elif value_lower in _BOOL_FALSE:
        target = next((s for s in samples if s.lower() in _BOOL_FALSE), None)
    else:
        target = None
    return target if target is not None else value


def _parse_detail(detail: str) -> tuple[str, str] | None:
    """"kpi {kid}.filter" -> (kid, "filter"); "kpi {kid}.numerator.filter"
    -> (kid, "numerator") — mirrors exactly how ground.py's _as_filter built
    the `where` string, the only producer of this detail shape."""
    if not detail.startswith("kpi "):
        return None
    parts = detail[len("kpi "):].split(".")
    if len(parts) == 2 and parts[1] == "filter" and parts[0]:
        return parts[0], "filter"
    if len(parts) == 3 and parts[1] in ("numerator", "denominator") and parts[2] == "filter" and parts[0]:
        return parts[0], parts[1]
    return None


def _broken_filter_refs(spec: DashboardSpec) -> list[tuple[str, str, str]]:
    """(kpi_id, field, column) for each still-unresolved missing_filter_value
    warning on this spec."""
    out: list[tuple[str, str, str]] = []
    for w in spec.warnings:
        if w.code != "missing_filter_value":
            continue
        parsed = _parse_detail(w.detail)
        if parsed is not None and w.column:
            out.append((parsed[0], parsed[1], w.column))
    return out


def _sample_values_for(
    kpi: Kpi, column: str, *,
    approved_columns: list[dict[str, Any]] | None,
    columns_by_dataset: dict[str, list[dict[str, Any]]] | None,
) -> list[str]:
    pool = (columns_by_dataset or {}).get(kpi.dataset_id, []) if columns_by_dataset is not None \
        else (approved_columns or [])
    for c in pool:
        if c.get("name") == column:
            return list(c.get("sample_values") or [])
    return []


def repair_missing_filters(
    spec: DashboardSpec, *,
    objective: str,
    approved_columns: list[dict[str, Any]] | None = None,
    columns_by_dataset: dict[str, list[dict[str, Any]]] | None = None,
    broker: Any, tier: str, complete_json_fn: CompleteJsonFn,
) -> DashboardSpec:
    """Best-effort: fix what can be safely fixed with one narrow follow-up
    call, drop the whole KPI for anything that stays unresolved, before this
    spec ever reaches C09. Returns `spec` unchanged if there was nothing to
    do — this is purely additive, never a new way to fail."""
    refs = _broken_filter_refs(spec)
    if not refs:
        return spec

    kpis_by_id = {k.kpi_id: k for k in spec.kpis}
    samples_by_ref: dict[tuple[str, str], list[str]] = {}
    col_by_ref: dict[tuple[str, str], str] = {}
    items: list[dict[str, Any]] = []
    for kid, field, col in refs:
        col_by_ref[(kid, field)] = col
        kpi = kpis_by_id.get(kid)
        if kpi is None:
            continue
        samples = _sample_values_for(kpi, col, approved_columns=approved_columns,
                                     columns_by_dataset=columns_by_dataset)
        samples_by_ref[(kid, field)] = samples
        if samples:  # nothing real to offer -> stays unresolved, no LLM call needed
            items.append({"kpi_id": kid, "field": field, "kpi_name": kpi.name,
                          "column": col, "sample_values": samples})

    fills: list[Any] = []
    if items:
        system, user = build_filter_repair_prompt(items=items, objective=objective)
        try:
            raw = complete_json_fn(broker, tier, system, user, FILTER_REPAIR_SCHEMA)
        except Exception:  # noqa: BLE001 — best-effort, never blocks the caller
            raw = None
        parsed_fills = raw.get("fills") if isinstance(raw, dict) else None
        if isinstance(parsed_fills, list):
            fills = parsed_fills

    patched_kpis = list(spec.kpis)
    resolved: set[tuple[str, str]] = set()
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        kid, field = fill.get("kpi_id"), fill.get("field")
        # Schema now requires "value" (see FILTER_REPAIR_SCHEMA), but a
        # provider that doesn't enforce it strictly has been observed
        # (live, gemini-flash-latest) substituting an unlisted "name" key
        # for the same answer — fall back to it rather than reading that
        # as a decline.
        value = fill.get("value")
        if value is None and "name" in fill:
            value = fill.get("name")
        if value is None or not isinstance(kid, str) or field not in _FIELDS:
            continue
        ref = (kid, field)
        samples = samples_by_ref.get(ref)
        if not samples:
            continue
        value = _normalize_boolean_fill(str(value), samples)
        if str(value) not in [str(v) for v in samples]:
            continue  # not a real sample value — never invent, skip
        idx = next((i for i, k in enumerate(patched_kpis) if k.kpi_id == kid), None)
        if idx is None:
            continue
        kpi = patched_kpis[idx]
        new_filter = KpiFilter(column=col_by_ref[ref], operator="equals", value=value)
        if field == "filter":
            patched_kpis[idx] = kpi.model_copy(update={"filter": new_filter})
        elif field == "numerator" and kpi.numerator is not None:
            patched_kpis[idx] = kpi.model_copy(
                update={"numerator": kpi.numerator.model_copy(update={"filter": new_filter})})
        elif field == "denominator" and kpi.denominator is not None:
            patched_kpis[idx] = kpi.model_copy(
                update={"denominator": kpi.denominator.model_copy(update={"filter": new_filter})})
        else:
            continue
        resolved.add(ref)

    unresolved_refs = [(kid, field) for kid, field, _col in refs if (kid, field) not in resolved]
    kpi_ids_to_drop = {kid for kid, _field in unresolved_refs}
    if not resolved and not kpi_ids_to_drop:
        return spec

    patched_kpis = [k for k in patched_kpis if k.kpi_id not in kpi_ids_to_drop]

    # Cascade: dropping a KPI leaves any Analysis whose `metric` pointed at
    # it dangling, and in turn any Visualization whose `source_ref` pointed
    # at either the dropped KPI directly (a kpi_card) or one of those now-
    # dropped Analyses (a bar/donut/etc.). Before this cascade existed, the
    # KPI vanished here but its dependents survived unchanged, silently
    # reappearing several stages later — live, as C14 dashboard composition
    # rejecting a kpi_card with "chart_type_mismatch: kpi_card must bind to
    # a kpi_id" — a confusing symptom pointing nowhere near the real cause.
    # An Analysis is DROPPED outright, not left with metric=None: falling
    # back to a bare grouped_count_rows would silently swap "renewal rate by
    # region" for "contract count by region" under the same chart, the exact
    # wrong-number-that-looks-legitimate failure this whole module exists to
    # prevent for KPIs.
    patched_analyses = list(spec.analyses)
    dropped_analysis_ids: set[str] = set()
    if kpi_ids_to_drop:
        kept_analyses = []
        for a in patched_analyses:
            if a.metric in kpi_ids_to_drop:
                dropped_analysis_ids.add(a.analysis_id)
            else:
                kept_analyses.append(a)
        patched_analyses = kept_analyses

    dangling_refs = kpi_ids_to_drop | dropped_analysis_ids
    patched_visualizations = list(spec.visualizations)
    dropped_chart_ids: set[str] = set()
    if dangling_refs:
        kept_viz = []
        for v in patched_visualizations:
            if v.source_ref in dangling_refs:
                dropped_chart_ids.add(v.chart_id)
            else:
                kept_viz.append(v)
        patched_visualizations = kept_viz

    remaining_warnings: list[SpecWarning] = []
    for w in spec.warnings:
        if w.code == "missing_filter_value":
            parsed = _parse_detail(w.detail)
            if parsed is not None:
                if parsed in resolved:
                    continue  # fixed — no warning needed at all
                if parsed[0] in kpi_ids_to_drop:
                    # Visible, but not spec-fatal — the unsafe KPI is gone,
                    # not left half-filtered.
                    remaining_warnings.append(SpecWarning(
                        code="dropped_unresolvable_kpi", column=w.column,
                        detail=f"{w.detail} — dropped after the filter micro-repair "
                               "could not safely resolve it"))
                    continue
        remaining_warnings.append(w)
    for aid in dropped_analysis_ids:
        remaining_warnings.append(SpecWarning(
            code="dropped_dangling_analysis", column="",
            detail=f"analysis {aid} dropped — its metric KPI was dropped above"))
    for cid in dropped_chart_ids:
        remaining_warnings.append(SpecWarning(
            code="dropped_dangling_visualization", column="",
            detail=f"visualization {cid} dropped — its source_ref was dropped above"))

    return spec.model_copy(update={
        "kpis": patched_kpis, "analyses": patched_analyses,
        "visualizations": patched_visualizations, "warnings": remaining_warnings,
    })
