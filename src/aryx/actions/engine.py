"""Action execution engine (G13): guard -> effects -> audit log.

Effects v1: set_attribute, add_relationship, remove_relationship, set_label.
No entity deletes, no source-system writeback (v2 — do not oversell).

Effects apply to Postgres (the source of truth) FIRST and touch the
entity's ``updated_at`` so the projector's dirty-set picks it up; the graph
is a projection and is never mutated directly by this module.

The guard reuses the EXACT when-clause matcher from reasoning/engine.py —
one condition grammar across rules, axioms, and actions.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.reasoning.engine import _match as check_guard  # noqa: F401  (re-export)

logger = logging.getLogger(__name__)

EFFECT_KINDS = {"set_attribute", "add_relationship", "remove_relationship",
                "set_label"}
APPROVALS = {"required", "auto"}


def validate_definition(definition: dict[str, Any]) -> list[str]:
    """Return a list of problems with an action definition (empty = valid)."""
    problems = []
    if not definition.get("name"):
        problems.append("missing name")
    if not definition.get("applies_to"):
        problems.append("missing applies_to (ontology type)")
    if definition.get("approval", "required") not in APPROVALS:
        problems.append("approval must be 'required' or 'auto'")
    effects = definition.get("effects") or []
    if not effects:
        problems.append("at least one effect required")
    for i, effect in enumerate(effects):
        kinds = set(effect.keys()) & EFFECT_KINDS
        if len(kinds) != 1:
            problems.append(f"effect[{i}] must have exactly one of "
                            f"{sorted(EFFECT_KINDS)}")
    for pname, spec in (definition.get("params") or {}).items():
        if not isinstance(spec, dict) or "type" not in spec:
            problems.append(f"param '{pname}' needs a type")
    return problems


def validate_params(definition: dict[str, Any],
                    params: dict[str, Any]) -> list[str]:
    """Check required params are present (empty list = OK)."""
    problems = []
    for pname, spec in (definition.get("params") or {}).items():
        if spec.get("required") and pname not in params:
            problems.append(f"missing required param '{pname}'")
    return problems


def _render(value: Any, params: dict[str, Any]) -> Any:
    """Substitute ``{param}`` placeholders in string effect values."""
    if isinstance(value, str):
        try:
            return value.format(**params)
        except (KeyError, IndexError):
            return value
    return value


def apply_effects(store: Any, entity_id: int, effects: list[dict[str, Any]],
                  params: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply one action's effects to Postgres; return the before/after log.

    Args:
        store: ActionStore (owns the entity attribute/relationship SQL).
        entity_id: Target entity.
        effects: The action definition's effect list.
        params: Validated execution parameters (placeholder substitution).

    Returns:
        effect_log rows — one per effect with before/after for the audit.
    """
    log: list[dict[str, Any]] = []
    for effect in effects:
        kind = next(iter(set(effect.keys()) & EFFECT_KINDS))
        spec = effect[kind]
        if kind == "set_attribute":
            key = spec["key"]
            value = _render(spec.get("value"), params)
            before = store.get_attribute(entity_id, key)
            if before == value:
                log.append({"effect": kind, "key": key, "no_op": True})
                continue
            store.set_attribute(entity_id, key, value)
            log.append({"effect": kind, "key": key,
                        "before": before, "after": value})
        elif kind == "set_label":
            value = _render(spec.get("value") or spec, params)
            before = store.get_attribute(entity_id, "inferred_label")
            store.set_attribute(entity_id, "inferred_label", value)
            log.append({"effect": kind, "before": before, "after": value})
        elif kind == "add_relationship":
            target = store.find_entity(spec["target_type"],
                                       _render(spec["target_name"], params))
            if target is None:
                log.append({"effect": kind, "error": "target not found",
                            "target": spec.get("target_name")})
                continue
            store.add_relationship(entity_id, target, spec["name"])
            log.append({"effect": kind, "name": spec["name"],
                        "target_entity_id": target})
        elif kind == "remove_relationship":
            removed = store.remove_relationship(entity_id, spec["name"])
            log.append({"effect": kind, "name": spec["name"],
                        "removed": removed})
    logger.info("effects applied entity=%s count=%d", entity_id, len(log))
    return log
