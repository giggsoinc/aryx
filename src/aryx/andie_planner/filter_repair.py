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
        kid, field, value = fill.get("kpi_id"), fill.get("field"), fill.get("value")
        if value is None or not isinstance(kid, str) or field not in _FIELDS:
            continue
        ref = (kid, field)
        samples = samples_by_ref.get(ref)
        if not samples or str(value) not in [str(v) for v in samples]:
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

    return spec.model_copy(update={"kpis": patched_kpis, "warnings": remaining_warnings})
