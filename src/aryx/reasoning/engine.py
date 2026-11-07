"""Forward-chaining rule evaluator over the workspace entity store.

Rule DSL (JSON):
  when: {"type": "Customer", "attr": "revenue", "op": ">", "value": 1000000}
  then: {"set_label": "Platinum"}  OR  {"add_relationship": "TIER_MEMBER",
                                        "target_type": "Tier",
                                        "target_name": "Platinum"}

Each match writes either an inferred label for the source entity or an
INF_<NAME> edge between two entities, into the inferred tables (never into the
asserted data). Every evaluation rebuilds those tables from scratch in one
transaction, so it is idempotent — re-running over the same data produces the
same result — and stale output from a deleted rule never lingers.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.config import get_settings
from aryx.reasoning.edge_axioms import apply_edge_axiom
from aryx.store.entity_store import EntityStore
from aryx.store.inferred_store import InferredStore
from aryx.store.rule_store import RuleStore

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


def _entity_dict(row: tuple) -> dict:
    """Shape an (id, ontology_type, attributes) row the way _match expects."""
    return {"id": row[0], "type": row[1], "attributes": row[2]}


def _fire(store: InferredStore, entity: dict, then: dict, rule_name: str) -> int:
    """Apply the then-clause; return 1 on success, 0 on no-op."""
    eid = int(entity.get("id", 0))
    if not eid:
        return 0
    if "set_label" in then:
        store.set_label(eid, str(then["set_label"]), rule_name)
        return 1
    if "add_relationship" in then:
        store.add_named_target_edge(
            eid, f"INF_{str(then['add_relationship']).upper()}",
            str(then.get("target_type", "")), str(then.get("target_name", "")),
            rule_name)
        return 1
    return 0


def _run_rule(store: InferredStore, rule: dict, entities: list[dict]) -> int:
    """Evaluate one rule against the workspace; return its fire count."""
    when = rule.get("when") or {}
    then = rule.get("then") or {}
    name = str(rule["name"])
    if "edge" in when:
        # Edge-scoped axiom (inverse_of / symmetric / transitive).
        return apply_edge_axiom(store, str(when["edge"]), then, name)
    return sum(_fire(store, ent, then, name) for ent in entities if _match(ent, when))


def evaluate_workspace(workspace_id: int) -> dict[str, Any]:
    """Apply every enabled rule against the workspace; return per-rule fire counts."""
    settings = get_settings()
    rules_store = RuleStore(settings.rdb_dsn)
    try:
        rules = [r for r in rules_store.list_(workspace_id) if r["enabled"]]
    finally:
        rules_store.close()
    entities: list[dict] = []
    if rules:
        estore = EntityStore(settings.rdb_dsn, workspace_id)
        try:
            entities = [_entity_dict(r) for r in estore.list_entities()]
        finally:
            estore.close()
    per_rule: dict[str, int] = {}
    # One transaction: clear, then rebuild. A failure leaves the previous
    # inferred output untouched instead of a half-built one.
    with InferredStore(settings.rdb_dsn, workspace_id) as store:
        store.clear()
        for rule in rules:
            per_rule[rule["name"]] = _run_rule(store, rule, entities)
    if not rules:
        return {"rules_evaluated": 0, "total_fires": 0, "per_rule": {}}
    bumps = RuleStore(settings.rdb_dsn)
    try:
        for name, fires in per_rule.items():
            if fires:
                bumps.bump(workspace_id, name, fires)
    finally:
        bumps.close()
    total = sum(per_rule.values())
    logger.info("evaluator ws=%s fires=%d rules=%d",
                workspace_id, total, len(rules))
    return {"rules_evaluated": len(rules), "total_fires": total,
            "per_rule": per_rule}
