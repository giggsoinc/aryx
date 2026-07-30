"""Steps 5-7 of the Execution Compiler procedure: resource/row limits,
template-binding checks, and acyclic verification for a compiled node list.

Purely structural — never a re-check of C09's business-rule validation
(numeric measures, ratio operand presence, operation whitelisting are
already guaranteed by the time compile.py runs).
"""
from __future__ import annotations

from aryx.execution_compiler.models import CompilationIssue, ExecutionNode
from aryx.execution_compiler.templates import TEMPLATES


def validate_bindings(nodes: list[ExecutionNode]) -> list[CompilationIssue]:
    """Every node's template must be a known, vetted one (templates.py) with
    exactly its required parameter keys, a unique node_id, and dependencies
    that resolve to another node in the same plan."""
    issues: list[CompilationIssue] = []
    seen: set[str] = set()
    for node in nodes:
        if node.node_id in seen:
            issues.append(CompilationIssue(code="duplicate_node_id", node_id=node.node_id))
        seen.add(node.node_id)
        required = TEMPLATES.get(node.template)
        if required is None:
            issues.append(CompilationIssue(code="unknown_template", node_id=node.node_id,
                                           detail=node.template))
            continue
        actual = frozenset(node.parameters.keys())
        if actual != required:
            issues.append(CompilationIssue(
                code="parameter_mismatch", node_id=node.node_id,
                detail=f"template {node.template!r} expects {sorted(required)}, got {sorted(actual)}"))
    for node in nodes:
        for dep in node.depends_on:
            if dep not in seen:
                issues.append(CompilationIssue(code="dangling_dependency", node_id=node.node_id,
                                               detail=dep))
    return issues


def is_acyclic(nodes: list[ExecutionNode]) -> bool:
    """Kahn's algorithm: True iff the dependency graph has no cycle.

    A dependency naming a node_id outside this plan is ignored here (already
    reported as `dangling_dependency` by validate_bindings) so one bad
    reference doesn't also mask the real acyclic/cyclic verdict.
    """
    by_id = {n.node_id: n for n in nodes}
    indegree = {n.node_id: 0 for n in nodes}
    children: dict[str, list[str]] = {n.node_id: [] for n in nodes}
    for node in nodes:
        for dep in node.depends_on:
            if dep in by_id:
                children[dep].append(node.node_id)
                indegree[node.node_id] += 1

    queue = [node_id for node_id, deg in indegree.items() if deg == 0]
    visited = 0
    while queue:
        current = queue.pop()
        visited += 1
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return visited == len(nodes)


def check_resource_limits(nodes: list[ExecutionNode], node_limit: int) -> list[CompilationIssue]:
    """Step 5: reject a plan that would compile more nodes than node_limit —
    an engineering safety cap, not a spec'd number (mirrors C10's THRESHOLD:
    flagged here as adjustable, not authoritative)."""
    if len(nodes) > node_limit:
        return [CompilationIssue(code="node_limit_exceeded",
                                 detail=f"{len(nodes)} nodes exceeds node_limit={node_limit}")]
    return []
