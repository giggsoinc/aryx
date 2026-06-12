"""G13: action DSL validation, guard gating, effects + audit log."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Stub graph/db deps so aryx.reasoning (guard matcher source) imports clean
for _mod in ("falkordb", "psycopg", "psycopg.types", "psycopg.types.json",
             "psycopg_pool"):
    sys.modules.setdefault(_mod, MagicMock())

from aryx.actions.engine import (apply_effects, check_guard,
                                 validate_definition, validate_params)

_DEF = {
    "name": "flag_sole_source_supplier",
    "applies_to": "Supplier",
    "guard": {"attr": "alternate_count", "op": "==", "value": 0},
    "params": {"reason": {"type": "string", "required": True}},
    "effects": [
        {"set_attribute": {"key": "risk_flag", "value": "SOLE_SOURCE"}},
        {"add_relationship": {"name": "ESCALATED_TO", "target_type": "Team",
                              "target_name": "Procurement"}},
    ],
    "approval": "required",
}


def test_valid_definition_passes() -> None:
    """The spec's example definition validates clean."""
    assert validate_definition(_DEF) == []


def test_definition_problems_reported() -> None:
    """Missing name/applies_to/effects and bad approval all surface."""
    problems = validate_definition({"approval": "yolo", "effects": []})
    assert len(problems) >= 3


def test_effect_must_have_exactly_one_kind() -> None:
    """An effect with zero or two kinds is rejected."""
    bad = dict(_DEF, effects=[{"set_attribute": {}, "set_label": {}}])
    assert any("exactly one" in p for p in validate_definition(bad))


def test_required_param_enforced() -> None:
    """Missing required param blocks execution."""
    assert validate_params(_DEF, {}) == ["missing required param 'reason'"]
    assert validate_params(_DEF, {"reason": "audit"}) == []


def test_guard_gates_execution() -> None:
    """Guard reuses the rules-engine matcher: same grammar, same result."""
    entity_blocked = {"type": "Supplier", "attributes": {"alternate_count": 2}}
    entity_fires = {"type": "Supplier", "attributes": {"alternate_count": 0}}
    assert check_guard(entity_fires, _DEF["guard"]) is True
    assert check_guard(entity_blocked, _DEF["guard"]) is False


def test_effects_write_postgres_first_with_audit() -> None:
    """set_attribute + add_relationship land in the store with before/after."""
    store = MagicMock()
    store.get_attribute.return_value = None
    store.find_entity.return_value = 42
    log = apply_effects(store, 7, _DEF["effects"], {"reason": "x"})
    store.set_attribute.assert_called_once_with(7, "risk_flag", "SOLE_SOURCE")
    store.add_relationship.assert_called_once_with(7, 42, "ESCALATED_TO")
    assert log[0]["before"] is None and log[0]["after"] == "SOLE_SOURCE"
    assert log[1]["target_entity_id"] == 42


def test_idempotent_reapply_is_noop() -> None:
    """Re-applying an already-set attribute records no_op, writes nothing."""
    store = MagicMock()
    store.get_attribute.return_value = "SOLE_SOURCE"
    log = apply_effects(store, 7, [_DEF["effects"][0]], {})
    store.set_attribute.assert_not_called()
    assert log[0]["no_op"] is True


def test_param_placeholder_substitution() -> None:
    """{param} placeholders render into effect values."""
    store = MagicMock()
    store.get_attribute.return_value = None
    effects = [{"set_attribute": {"key": "note", "value": "by {reason}"}}]
    log = apply_effects(store, 1, effects, {"reason": "steward"})
    assert log[0]["after"] == "by steward"


def test_missing_relationship_target_logged_not_raised() -> None:
    """A missing target is an audit-log error row, not an exception."""
    store = MagicMock()
    store.find_entity.return_value = None
    log = apply_effects(store, 1, [_DEF["effects"][1]], {})
    assert log[0]["error"] == "target not found"
    store.add_relationship.assert_not_called()


def test_remove_relationship_reports_count() -> None:
    """remove_relationship logs how many rows went away."""
    store = MagicMock()
    store.remove_relationship.return_value = 2
    log = apply_effects(store, 1,
                        [{"remove_relationship": {"name": "ESCALATED_TO"}}],
                        {})
    assert log[0]["removed"] == 2
