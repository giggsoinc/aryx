"""G3x: survivorship strategy tests — determinism, conflicts, overrides."""
from __future__ import annotations

import random

from aryx.resolution.golden import golden_record_with_policy
from aryx.resolution.survivorship import SurvivorshipPolicy

_MEMBERS = [
    {"payload": {"name": "Apex Corp", "revenue": 100, "city": "LA"},
     "record_id": 1, "source_system": "portal", "cleaned_at": "2026-01-01"},
    {"payload": {"name": "Apex Corporation", "revenue": 200},
     "record_id": 2, "source_system": "sap", "cleaned_at": "2026-03-01"},
    {"payload": {"name": "Apex Corp", "revenue": 200, "city": "Los Angeles",
                 "country": "US"},
     "record_id": 3, "source_system": "crm", "cleaned_at": "2026-02-01"},
]


def test_first_non_empty_takes_input_order() -> None:
    """Legacy default: first member's value wins."""
    merged, _, _ = golden_record_with_policy(_MEMBERS, SurvivorshipPolicy())
    assert merged["name"] == "Apex Corp"
    assert merged["revenue"] == 100


def test_source_priority_winner() -> None:
    """SAP beats portal and crm when ranked first."""
    policy = SurvivorshipPolicy(default_strategy="source_priority",
                                source_priority=["sap", "crm", "portal"])
    merged, prov, _ = golden_record_with_policy(_MEMBERS, policy)
    assert merged["name"] == "Apex Corporation"
    assert prov["name"] == 2


def test_most_recent_winner() -> None:
    """Newest cleaned_at wins (record-level recency)."""
    policy = SurvivorshipPolicy(default_strategy="most_recent")
    merged, prov, _ = golden_record_with_policy(_MEMBERS, policy)
    assert merged["name"] == "Apex Corporation"  # record 2, 2026-03-01
    assert prov["revenue"] == 2


def test_most_complete_winner() -> None:
    """Member with most non-empty keys wins (record 3 has 4 keys)."""
    policy = SurvivorshipPolicy(default_strategy="most_complete")
    merged, prov, _ = golden_record_with_policy(_MEMBERS, policy)
    assert prov["name"] == 3
    assert merged["city"] == "Los Angeles"


def test_most_frequent_winner() -> None:
    """Modal value wins: 'Apex Corp' appears twice."""
    policy = SurvivorshipPolicy(default_strategy="most_frequent")
    merged, _, _ = golden_record_with_policy(_MEMBERS, policy)
    assert merged["name"] == "Apex Corp"
    assert merged["revenue"] == 200


def test_per_attribute_override() -> None:
    """revenue uses most_recent while default stays source_priority."""
    policy = SurvivorshipPolicy(
        default_strategy="source_priority",
        source_priority=["portal", "sap", "crm"],
        attribute_strategies={"revenue": "most_recent"})
    merged, prov, _ = golden_record_with_policy(_MEMBERS, policy)
    assert merged["name"] == "Apex Corp"      # portal first
    assert prov["revenue"] == 2               # newest record


def test_order_independence_all_strategies_except_legacy() -> None:
    """Shuffling member order never changes the result (10 shuffles)."""
    rng = random.Random(7)
    for strategy in ("source_priority", "most_recent", "most_complete",
                     "most_frequent"):
        policy = SurvivorshipPolicy(default_strategy=strategy,
                                    source_priority=["sap", "crm", "portal"])
        baseline, _, _ = golden_record_with_policy(_MEMBERS, policy)
        for _ in range(10):
            shuffled = list(_MEMBERS)
            rng.shuffle(shuffled)
            merged, _, _ = golden_record_with_policy(shuffled, policy)
            assert merged == baseline, f"{strategy} is order-dependent"


def test_conflict_rows_per_disputed_attribute() -> None:
    """Exactly one conflict row per attribute with >1 distinct value."""
    policy = SurvivorshipPolicy(default_strategy="most_recent")
    _, _, conflicts = golden_record_with_policy(_MEMBERS, policy)
    disputed = {c["attribute"] for c in conflicts}
    assert disputed == {"name", "revenue", "city"}
    name_conflict = next(c for c in conflicts if c["attribute"] == "name")
    losers = {l["value"] for l in name_conflict["losing_values"]}
    assert losers == {"Apex Corp"}
    assert name_conflict["strategy"] == "most_recent"


def test_undisputed_attribute_no_conflict() -> None:
    """country exists once -> no conflict row."""
    _, _, conflicts = golden_record_with_policy(
        _MEMBERS, SurvivorshipPolicy(default_strategy="most_frequent"))
    assert "country" not in {c["attribute"] for c in conflicts}


def test_policy_from_json_ignores_unknown_keys() -> None:
    """Stored JSON round-trips; junk keys and strategies are tolerated."""
    policy = SurvivorshipPolicy.from_json(
        {"default_strategy": "most_recent", "junk": 1,
         "attribute_strategies": {"x": "not_a_strategy"}})
    assert policy.default_strategy == "most_recent"
    assert policy.strategy_for("x") == "first_non_empty"


def test_empty_members() -> None:
    """No members -> empty everything."""
    merged, prov, conflicts = golden_record_with_policy(
        [], SurvivorshipPolicy())
    assert merged == {} and prov == {} and conflicts == []
