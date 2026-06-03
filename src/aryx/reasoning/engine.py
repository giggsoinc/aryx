"""Forward-chaining rule evaluator over the workspace entity store.

Rule DSL (JSON):
  when: {"type": "Customer", "attr": "revenue", "op": ">", "value": 1000000}
  then: {"set_label": "Platinum"}  OR  {"add_relationship": "TIER_MEMBER",
                                        "target_type": "Tier",
                                        "target_name": "Platinum"}

Each match writes either a label attribute (`inferred_label`) on the source
entity in FalkorDB or an INF_<NAME> edge between two entities. The evaluator
is idempotent — re-running over the same data produces the same graph.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.config import get_settings
from aryx.graph.falkor_store import FalkorStore
from aryx.store.entity_store import EntityStore
from aryx.store.rule_store import RuleStore
from aryx.workspaces import ws_graph

logger = logging.getLogger(__name__)

_OPS = {
    ">":  lambda a, b: float(a) > float(b),
    ">=": lambda a, b: float(a) >= float(b),
    "<":  lambda a, b: float(a) < float(b),
    "<=": lambda a, b: float(a) <= float(b),
    "==": lambda a, b: str(a) == str(b),
    "!=": lambda a, b: str(a) != str(b),
    "contains": lambda a, b: str(b).lower() in str(a or "").lower(),
}


def _match(entity: dict, when: dict) -> bool:
    """Test one entity against one when-clause."""
    if when.get("type") and entity.get("type") != when["type"]:
        return False
    attr = when.get("attr")
    op = _OPS.get(when.get("op", "=="))
    if not attr or op is None:
        return False
    val = (entity.get("attributes") or {}).get(attr)
    if val is None:
        return False
    try:
        return op(val, when.get("value"))
    except (TypeError, ValueError):
        return False


def _apply_label(graph: FalkorStore, entity_id: int, label: str) -> None:
    """Write an inferred_label attribute on the entity in FalkorDB."""
    graph.run(
        "MATCH (n {id: $id}) SET n.inferred_label = $label",
        params={"id": int(entity_id), "label": str(label)},
    )


def _apply_edge(graph: FalkorStore, source_id: int, name: str,
                target_type: str, target_name: str) -> None:
    """Create an INF_-prefixed edge to a target entity (matched by type+name)."""
    rel = f"INF_{name.upper()}"
    graph.run(
        "MATCH (s {id: $sid}), (t {ontology_type: $ttype, name: $tname}) "
        f"MERGE (s)-[r:{rel} {{inferred: true}}]->(t)",
        params={"sid": int(source_id), "ttype": target_type,
                "tname": target_name},
    )


def _fire(graph: FalkorStore, entity: dict, then: dict) -> int:
    """Apply the then-clause; return 1 on success, 0 on no-op."""
    eid = int(entity.get("id", 0))
    if not eid:
        return 0
    if "set_label" in then:
        _apply_label(graph, eid, str(then["set_label"]))
        return 1
    if "add_relationship" in then:
        _apply_edge(
            graph, eid, str(then["add_relationship"]),
            str(then.get("target_type", "")),
            str(then.get("target_name", "")),
        )
        return 1
    return 0


def evaluate_workspace(workspace_id: int) -> dict[str, Any]:
    """Apply every enabled rule against the workspace; return per-rule fire counts."""
    settings = get_settings()
    rules_store = RuleStore(settings.rdb_dsn)
    try:
        rules = [r for r in rules_store.list_(workspace_id) if r["enabled"]]
    finally:
        rules_store.close()
    if not rules:
        return {"rules_evaluated": 0, "total_fires": 0, "per_rule": {}}
    estore = EntityStore(settings.rdb_dsn, workspace_id)
    try:
        ents = estore.list_entities()
    finally:
        estore.close()
    graph = FalkorStore(settings.graph_url, ws_graph(workspace_id))
    per_rule: dict[str, int] = {}
    total = 0
    bumps = RuleStore(settings.rdb_dsn)
    try:
        for rule in rules:
            fires = 0
            for ent in ents:
                if _match(ent, rule.get("when") or {}):
                    fires += _fire(graph, ent, rule.get("then") or {})
            per_rule[rule["name"]] = fires
            total += fires
            if fires:
                bumps.bump(workspace_id, rule["name"], fires)
    finally:
        bumps.close()
    logger.info("evaluator ws=%s fires=%d rules=%d",
                workspace_id, total, len(rules))
    return {"rules_evaluated": len(rules), "total_fires": total,
            "per_rule": per_rule}
