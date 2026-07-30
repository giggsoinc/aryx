"""C12 — Deterministic Analysis Execution: run a compiled C11 ExecutionPlan's
node DAG against real (C10-converted) rows.

No LLM. Every node dispatches to one of C11's vetted templates only — same
"Key control" as the compiler itself: an unknown template never executes,
it fails the node instead (see run_plan's per-node try/except).
"""
from __future__ import annotations

import time
from typing import Any

from aryx.execution_compiler.models import ExecutionNode, ExecutionPlan

_NUMERIC_TEMPLATES = {"sum_numeric", "average_numeric", "median_numeric"}
_GROUPED_NUMERIC_TEMPLATES = {
    "grouped_sum_numeric": "sum", "grouped_average_numeric": "average",
    "grouped_median_numeric": "median",
}


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


def _aggregate(values: list[float | None], op: str) -> dict[str, Any]:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return {"value": 0.0, "sample_size": 0, "excluded_null_rows": len(values)}
    return {"value": _central_tendency(op, non_null), "sample_size": len(non_null),
           "excluded_null_rows": len(values) - len(non_null)}


def _scalar(result: Any) -> float:
    """Coerce a count_rows (int) or a *_numeric (dict) node result to a bare number."""
    return float(result["value"]) if isinstance(result, dict) else float(result)


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


def _exec_node(node: ExecutionNode, rows: list[dict[str, Any]],
               results: dict[str, Any]) -> Any:
    """Execute one node against its dataset's rows, given upstream results."""
    p = node.parameters
    t = node.template

    if t == "filter_equals":
        return [i for i, r in enumerate(rows) if r.get(p["column"]) == p["value"]]
    if t == "filter_in":
        values = set(p["values"])
        return [i for i, r in enumerate(rows) if r.get(p["column"]) in values]

    upstream = results.get(node.depends_on[0]) if node.depends_on else None
    idx = upstream if upstream is not None else range(len(rows))

    if t == "count_rows":
        return len(list(idx))
    if t in _NUMERIC_TEMPLATES:
        values = [_numeric(rows[i].get(p["column"])) for i in idx]
        op = t.split("_")[0]  # sum_numeric -> sum, etc.
        return _aggregate(values, op)
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
        return {
            g: {"numerator": num_counts.get(g, 0), "denominator": d,
               "value": (num_counts.get(g, 0) / d) if d else None, "sample_size": d}
            for g, d in den_counts.items()
        }

    raise ValueError(f"unknown template {t!r}")


def run_plan(plan: ExecutionPlan, rows_by_dataset: dict[str, list[dict[str, Any]]], *,
            maximum_runtime_seconds: float = 30.0) -> tuple[dict[str, Any], list[str], int, int]:
    """Execute every node in dependency order.

    Returns (node_results, errors, nodes_completed, nodes_failed). A node
    that fails (unknown template, missing column) is recorded in `errors`
    and skipped — dependents referencing it simply get no result, same
    controlled-degradation contract as the rest of the pipeline.
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
            results[node.node_id] = _exec_node(node, rows, results)
            completed += 1
        except Exception as exc:  # noqa: BLE001 — one bad node must not crash the run
            errors.append(f"node {node.node_id!r} ({node.template!r}) failed: {exc}")
            failed += 1
    return results, errors, completed, failed
