"""C12 — Deterministic Analysis Execution: run a compiled C11 ExecutionPlan's
node DAG against real (C10-converted) rows.

No LLM. Every node dispatches to one of C11's vetted templates only — same
"Key control" as the compiler itself: an unknown template never executes,
it fails the node instead (see run_plan's per-node try/except).
"""
from __future__ import annotations

import statistics
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aryx.execution_compiler.models import ExecutionNode, ExecutionPlan
from aryx.store.graph_profile_store import GraphProfileStore

if TYPE_CHECKING:
    from aryx.ports.protocols import GraphReaderPort

_NUMERIC_TEMPLATES = {"sum_numeric", "average_numeric", "median_numeric"}
_GROUPED_NUMERIC_TEMPLATES = {
    "grouped_sum_numeric": "sum", "grouped_average_numeric": "average",
    "grouped_median_numeric": "median",
}
_GROUPED_2D_NUMERIC_TEMPLATES = {
    "grouped2d_sum_numeric": "sum", "grouped2d_average_numeric": "average",
    "grouped2d_median_numeric": "median",
}
# Gantt/scatter charts become unreadable past a few dozen bars/points — cap
# rather than silently truncate without a bound (never render thousands of
# raw rows, which no reference gantt/scatter chart does either).
MAX_GANTT_ROWS = 100
MAX_ROW_POINTS = 500
DEFAULT_HISTOGRAM_BUCKETS = 10


class RuntimeLimitExceeded(Exception):
    """Raised internally when maximum_runtime_seconds is hit mid-execution."""


def _is_null(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _numeric(v: Any) -> float | None:
    if _is_null(v):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("%", "").strip())
    except ValueError:
        return None


def _central_tendency(op: str, values: list[float]) -> float:
    if op == "sum":
        return sum(values)
    if op == "average":
        return sum(values) / len(values)
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _quartile_stats(values: list[float]) -> dict[str, float | None]:
    """min/q1/median/q3/max via linear-interpolation quartiles (`method=
    "inclusive"`, the conventional definition most BI/spreadsheet tools use).
    `values` must already be null-filtered by the caller."""
    if not values:
        return {"min": None, "q1": None, "median": None, "q3": None, "max": None}
    if len(values) == 1:
        v = values[0]
        return {"min": v, "q1": v, "median": v, "q3": v, "max": v}
    q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {"min": min(values), "q1": q1, "median": median, "q3": q3, "max": max(values)}


def _aggregate(values: list[float | None], op: str) -> dict[str, Any]:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return {"value": 0.0, "sample_size": 0, "excluded_null_rows": len(values)}
    return {"value": _central_tendency(op, non_null), "sample_size": len(non_null),
           "excluded_null_rows": len(values) - len(non_null)}


def _parse_date(v: Any) -> datetime | None:
    """Best-effort ISO-ish date parse — returns None (never a fabricated
    date) for anything that isn't a real, parseable value."""
    if _is_null(v):
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _histogram_buckets(values: list[float], bucket_count: int = DEFAULT_HISTOGRAM_BUCKETS) -> list[dict[str, float]]:
    """Equal-width bins between the observed min/max — `values` must already
    be null-filtered by the caller."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if lo == hi:
        return [{"bucket_start": lo, "bucket_end": hi, "count": float(len(values))}]
    width = (hi - lo) / bucket_count
    counts = [0] * bucket_count
    for v in values:
        idx = min(int((v - lo) / width), bucket_count - 1)
        counts[idx] += 1
    return [{"bucket_start": lo + i * width, "bucket_end": lo + (i + 1) * width, "count": float(counts[i])}
           for i in range(bucket_count)]


def _survival_curve(rows: list[dict[str, Any]], group_column: str,
                    start_column: str, end_column: str) -> dict[str, list[dict[str, float]]]:
    """Actuarial Kaplan-Meier estimator, one curve per group ("_all_" when
    ungrouped). A row with `end_column` set is an event (exit) at that
    duration; a row with it null is censored — still active as of the
    latest date observed anywhere in the cohort (never "today", which would
    make the curve depend on when the query happens to run rather than only
    on the data). Rows with no parseable `start_column` are dropped, never
    treated as duration 0."""
    by_group: dict[str, list[tuple[int, bool]]] = {}
    spans_by_group: dict[str, list[tuple[datetime, datetime | None]]] = {}
    latest_seen: datetime | None = None
    for r in rows:
        start = _parse_date(r.get(start_column))
        if start is None:
            continue
        end = _parse_date(r.get(end_column)) if end_column else None
        g = str(r.get(group_column)) if group_column else "_all_"
        spans_by_group.setdefault(g, []).append((start, end))
        for d in (start, end):
            if d is not None and (latest_seen is None or d > latest_seen):
                latest_seen = d
    as_of = latest_seen or datetime.now()

    for g, spans in spans_by_group.items():
        durations: list[tuple[int, bool]] = []
        for start, end in spans:
            duration = ((end or as_of) - start).days
            if duration < 0:
                continue
            durations.append((duration, end is not None))
        if durations:
            by_group[g] = durations

    result: dict[str, list[dict[str, float]]] = {}
    for g, durations in by_group.items():
        at_risk = len(durations)
        survival = 1.0
        points: list[dict[str, float]] = []
        for t in sorted({d for d, _ in durations}):
            events_at_t = sum(1 for d, is_event in durations if d == t and is_event)
            exits_at_t = sum(1 for d, _ in durations if d == t)
            if at_risk > 0 and events_at_t > 0:
                survival *= (1 - events_at_t / at_risk)
            points.append({"duration_days": float(t), "survived_fraction": survival, "at_risk": float(at_risk)})
            at_risk -= exits_at_t
        result[g] = points
    return result


def _scalar(result: Any) -> float:
    """Coerce a count_rows (int) or a *_numeric (dict) node result to a bare number."""
    return float(result["value"]) if isinstance(result, dict) else float(result)


def _kpi_result_from_node(result: Any) -> tuple[float | None, float | None, float | None, int, int]:
    """(value, numerator, denominator, sample_size, excluded_null_rows) from
    one node's raw execution result — shape depends on which template ran.
    Shared by analysis_execution.run (C12) and post_execution_validation
    (C13), which both need to turn a raw node result into KPI-level fields."""
    if isinstance(result, dict) and "numerator" in result:  # safe_ratio
        denominator = result["denominator"]
        return result["value"], result["numerator"], denominator, int(denominator or 0), 0
    if isinstance(result, dict) and "q1" in result:  # quartiles — median stands in as "value"
        return result["median"], None, None, result["sample_size"], result.get("excluded_null_rows", 0)
    if isinstance(result, dict) and "buckets" in result:  # histogram — no single scalar, never fabricated
        return None, None, None, result["sample_size"], result.get("excluded_null_rows", 0)
    if isinstance(result, dict):  # *_numeric aggregate
        return result["value"], None, None, result["sample_size"], result.get("excluded_null_rows", 0)
    return float(result), None, None, int(result), 0  # count_rows


def _topo_order(nodes: list[ExecutionNode]) -> list[ExecutionNode]:
    by_id = {n.node_id: n for n in nodes}
    order: list[ExecutionNode] = []
    visiting: set[str] = set()

    def visit(node: ExecutionNode) -> None:
        if node.node_id in visiting:
            return
        visiting.add(node.node_id)
        for dep in node.depends_on:
            if dep in by_id:
                visit(by_id[dep])
        order.append(node)

    for n in nodes:
        visit(n)
    return order


def resolve_graph_relation_nodes(dsn: str, workspace_id: int, plan: ExecutionPlan) -> None:
    """Resolve every `graph_relation_count` node's `path_id` to a concrete
    (source_type, relationship, target_type) triple, mutating `node.parameters`
    in place — C11's compiler has no graph/DB access, so this has to happen
    here, right before `run_plan`.

    Only 1-hop verified paths (path = [Type, REL, Type], depth 1) are
    supported. A path_id that isn't found, or names a deeper path, is left
    with only `path_id` in its parameters — `_exec_node`'s graph_relation_count
    branch then fails that one node cleanly (same controlled-degradation
    contract as an unknown template or a missing column), never silently
    truncating or inventing a shorter path.
    """
    if not any(n.template == "graph_relation_count" for n in plan.nodes):
        return
    store = GraphProfileStore(dsn, workspace_id)
    try:
        # GraphProfileStore's graph_id is a Postgres-side identifier, a
        # separate convention from ws_graph() (the FalkorDB graph NAME) —
        # confirmed against planning/run.py's own gstore.latest() call.
        profile = store.latest(f"graph_workspace_{workspace_id}")
    finally:
        store.close()
    if profile is None:
        return
    paths_by_id = {vp.path_id: vp for vp in profile.verified_paths}
    for node in plan.nodes:
        if node.template != "graph_relation_count":
            continue
        vp = paths_by_id.get(node.parameters.get("path_id", ""))
        if vp is None or len(vp.path) != 3:
            continue
        node.parameters = {
            **node.parameters,
            "source_type": vp.path[0], "relationship": vp.path[1],
            "target_type": vp.path[2], "direction": "out",
        }


def _exec_node(node: ExecutionNode, rows: list[dict[str, Any]],
               results: dict[str, Any], graph_reader: "GraphReaderPort | None" = None) -> Any:
    """Execute one node against its dataset's rows, given upstream results."""
    p = node.parameters
    t = node.template

    if t == "filter_equals":
        return [i for i, r in enumerate(rows) if r.get(p["column"]) == p["value"]]
    if t == "filter_in":
        values = set(p["values"])
        return [i for i, r in enumerate(rows) if r.get(p["column"]) in values]
    if t == "graph_relation_count":
        if graph_reader is None or "source_type" not in p:
            raise RuntimeError(
                f"graph_relation_count node {node.node_id!r}: unresolved or "
                f"unsupported graph path {p.get('path_id')!r}")
        return graph_reader.count_by_relationship(
            p["source_type"], p["relationship"], p["target_type"], p.get("direction", "out"))

    upstream = results.get(node.depends_on[0]) if node.depends_on else None
    idx = upstream if upstream is not None else range(len(rows))

    if t == "count_rows":
        return len(list(idx))
    if t in _NUMERIC_TEMPLATES:
        values = [_numeric(rows[i].get(p["column"])) for i in idx]
        op = t.split("_")[0]  # sum_numeric -> sum, etc.
        return _aggregate(values, op)
    if t == "quartiles_numeric":
        values = [_numeric(rows[i].get(p["column"])) for i in idx]
        non_null = [v for v in values if v is not None]
        return {**_quartile_stats(non_null), "sample_size": len(non_null),
               "excluded_null_rows": len(values) - len(non_null)}
    if t == "safe_ratio":
        num = _scalar(results[p["numerator_ref"]])
        den = _scalar(results[p["denominator_ref"]])
        return {"numerator": num, "denominator": den,
               "value": (num / den) if den else None}

    if t == "grouped_count_rows":
        counts: dict[str, int] = {}
        for r in rows:
            g = str(r.get(p["group_column"]))
            counts[g] = counts.get(g, 0) + 1
        return counts
    if t in _GROUPED_NUMERIC_TEMPLATES:
        op = _GROUPED_NUMERIC_TEMPLATES[t]
        buckets: dict[str, list[float]] = {}
        for r in rows:
            v = _numeric(r.get(p["column"]))
            if v is not None:
                g = str(r.get(p["group_column"]))
                buckets.setdefault(g, []).append(v)
        return {g: {"value": _central_tendency(op, vals), "sample_size": len(vals)}
               for g, vals in buckets.items()}
    if t == "grouped_safe_ratio":
        num_values = set(p["numerator_values"])
        den_values = set(p["denominator_values"])
        num_counts: dict[str, int] = {}
        den_counts: dict[str, int] = {}
        for r in rows:
            status = r.get(p["status_column"])
            if status not in den_values and status not in num_values:
                continue
            g = str(r.get(p["group_column"]))
            if status in den_values:
                den_counts[g] = den_counts.get(g, 0) + 1
            if status in num_values:
                num_counts[g] = num_counts.get(g, 0) + 1
        # Iterate the UNION of groups seen by either filter, not just
        # den_counts — numerator_values isn't guaranteed to be a subset of
        # denominator_values, so a group with numerator hits but zero
        # denominator hits must still appear (denominator=0, not silently
        # dropped from the chart).
        all_groups = set(num_counts) | set(den_counts)
        return {
            g: {"numerator": num_counts.get(g, 0), "denominator": den_counts.get(g, 0),
               "value": (num_counts.get(g, 0) / den_counts[g]) if den_counts.get(g) else None,
               "sample_size": den_counts.get(g, 0)}
            for g in all_groups
        }
    if t == "grouped_quartiles_numeric":
        buckets: dict[str, list[float]] = {}
        for r in rows:
            v = _numeric(r.get(p["column"]))
            if v is not None:
                g = str(r.get(p["group_column"]))
                buckets.setdefault(g, []).append(v)
        return {g: {**_quartile_stats(vals), "sample_size": len(vals)}
               for g, vals in buckets.items()}

    if t == "grouped2d_count_rows":
        counts2: dict[tuple[str, str], int] = {}
        for r in rows:
            key = (str(r.get(p["group_column"])), str(r.get(p["group_column_2"])))
            counts2[key] = counts2.get(key, 0) + 1
        return counts2
    if t in _GROUPED_2D_NUMERIC_TEMPLATES:
        op = _GROUPED_2D_NUMERIC_TEMPLATES[t]
        buckets2: dict[tuple[str, str], list[float]] = {}
        for r in rows:
            v = _numeric(r.get(p["column"]))
            if v is not None:
                key = (str(r.get(p["group_column"])), str(r.get(p["group_column_2"])))
                buckets2.setdefault(key, []).append(v)
        return {k: {"value": _central_tendency(op, vals), "sample_size": len(vals)}
               for k, vals in buckets2.items()}
    if t == "grouped2d_safe_ratio":
        num_values2 = set(p["numerator_values"])
        den_values2 = set(p["denominator_values"])
        num_counts2: dict[tuple[str, str], int] = {}
        den_counts2: dict[tuple[str, str], int] = {}
        for r in rows:
            status = r.get(p["status_column"])
            if status not in den_values2 and status not in num_values2:
                continue
            key = (str(r.get(p["group_column"])), str(r.get(p["group_column_2"])))
            if status in den_values2:
                den_counts2[key] = den_counts2.get(key, 0) + 1
            if status in num_values2:
                num_counts2[key] = num_counts2.get(key, 0) + 1
        all_cells = set(num_counts2) | set(den_counts2)
        return {
            k: {"numerator": num_counts2.get(k, 0), "denominator": den_counts2.get(k, 0),
               "value": (num_counts2.get(k, 0) / den_counts2[k]) if den_counts2.get(k) else None,
               "sample_size": den_counts2.get(k, 0)}
            for k in all_cells
        }

    if t == "row_points":
        label_col, x_col, y_col, size_col = (
            p["label_column"], p["x_column"], p["y_column"], p["size_column"])
        points: list[dict[str, Any]] = []
        for i, r in enumerate(rows):
            x = _numeric(r.get(x_col)) if x_col else None
            y = _numeric(r.get(y_col)) if y_col else None
            if x is None or y is None:
                continue
            size = _numeric(r.get(size_col)) if size_col else None
            label = str(r.get(label_col)) if label_col else str(i)
            points.append({"label": label, "x": x, "y": y, "size": size})
        return points[:MAX_ROW_POINTS]

    if t == "row_date_spans":
        label_col, start_col, end_col = p["label_column"], p["start_column"], p["end_column"]
        spans: list[dict[str, Any]] = []
        for i, r in enumerate(rows):
            start = r.get(start_col) if start_col else None
            if _is_null(start):
                continue
            end = r.get(end_col) if end_col else None
            label = str(r.get(label_col)) if label_col else str(i)
            spans.append({"label": label, "start": str(start),
                         "end": (str(end) if not _is_null(end) else None)})
        spans.sort(key=lambda s: s["start"])
        return spans[:MAX_GANTT_ROWS]

    if t == "survival_curve":
        return _survival_curve(rows, p["group_column"], p["start_column"], p["end_column"])

    if t == "histogram_buckets_numeric":
        values = [_numeric(rows[i].get(p["column"])) for i in idx]
        non_null = [v for v in values if v is not None]
        return {"buckets": _histogram_buckets(non_null), "sample_size": len(non_null),
               "excluded_null_rows": len(values) - len(non_null)}
    if t == "grouped_histogram_buckets_numeric":
        hist_buckets: dict[str, list[float]] = {}
        for r in rows:
            v = _numeric(r.get(p["column"]))
            if v is not None:
                g = str(r.get(p["group_column"]))
                hist_buckets.setdefault(g, []).append(v)
        return {g: {"buckets": _histogram_buckets(vals), "sample_size": len(vals)}
               for g, vals in hist_buckets.items()}

    raise ValueError(f"unknown template {t!r}")


def run_plan(plan: ExecutionPlan, rows_by_dataset: dict[str, list[dict[str, Any]]], *,
            maximum_runtime_seconds: float = 30.0,
            graph_reader: "GraphReaderPort | None" = None) -> tuple[dict[str, Any], list[str], int, int]:
    """Execute every node in dependency order.

    Returns (node_results, errors, nodes_completed, nodes_failed). A node
    that fails (unknown template, missing column) is recorded in `errors`
    and skipped — dependents referencing it simply get no result, same
    controlled-degradation contract as the rest of the pipeline.

    Args:
        graph_reader: only needed when `plan` has a `graph_relation_count`
            node (see resolve_graph_relation_nodes) — every other template is
            still pure/DB-free. None by default, fully backward compatible.
    """
    results: dict[str, Any] = {}
    errors: list[str] = []
    completed = 0
    failed = 0
    start = time.monotonic()
    for node in _topo_order(plan.nodes):
        if time.monotonic() - start > maximum_runtime_seconds:
            errors.append(f"maximum_runtime_seconds exceeded before node {node.node_id!r}")
            failed += len(plan.nodes) - completed - failed
            break
        rows = rows_by_dataset.get(node.dataset_id, [])
        try:
            results[node.node_id] = _exec_node(node, rows, results, graph_reader=graph_reader)
            completed += 1
        except Exception as exc:  # noqa: BLE001 — one bad node must not crash the run
            errors.append(f"node {node.node_id!r} ({node.template!r}) failed: {exc}")
            failed += 1
    return results, errors, completed, failed
