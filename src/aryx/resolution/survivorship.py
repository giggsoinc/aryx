"""Pluggable golden-record survivorship policies (G3).

Policies are plain JSON so an LLM skill can author them from a sentence like
"trust SAP over the supplier portal, prefer the newest value for revenue".
Recency is record-level (landed ``cleaned_at``) — attribute-level timestamps
do not exist and are not claimed.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

STRATEGIES = {"first_non_empty", "source_priority", "most_recent",
              "most_complete", "most_frequent"}

_EMPTY = (None, "", [], {})


@dataclass
class Contribution:
    """One member's value for one attribute, with merge-relevant metadata."""

    value: Any
    source_system: str | None
    cleaned_at: Any
    record_id: int
    completeness: int = 0


@dataclass
class SurvivorshipPolicy:
    """Declarative merge policy: a default strategy plus per-attribute overrides."""

    default_strategy: str = "first_non_empty"
    source_priority: list[str] = field(default_factory=list)
    attribute_strategies: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> "SurvivorshipPolicy":
        """Build a policy from stored JSON, ignoring unknown keys."""
        data = data or {}
        return cls(
            default_strategy=data.get("default_strategy", "first_non_empty"),
            source_priority=list(data.get("source_priority", [])),
            attribute_strategies=dict(data.get("attribute_strategies", {})),
        )

    def strategy_for(self, attribute: str) -> str:
        """Return the effective strategy for one attribute."""
        strategy = self.attribute_strategies.get(attribute, self.default_strategy)
        return strategy if strategy in STRATEGIES else "first_non_empty"


def _source_rank(c: Contribution, priority: list[str]) -> int:
    """Rank of a contribution's source (unknown sources rank last)."""
    try:
        return priority.index(c.source_system or "")
    except ValueError:
        return len(priority)


def _pick(contribs: list[Contribution], strategy: str,
          policy: SurvivorshipPolicy) -> Contribution:
    """Select the winning contribution. Deterministic for every strategy
    except first_non_empty (which is input-order dependent by design)."""
    if strategy == "first_non_empty":
        return contribs[0]
    if strategy == "source_priority":
        return min(contribs, key=lambda c: (_source_rank(c, policy.source_priority),
                                            c.record_id))
    if strategy == "most_recent":
        with_ts = [c for c in contribs if c.cleaned_at is not None]
        pool = with_ts or contribs
        newest = max(c.cleaned_at for c in pool) if with_ts else None
        candidates = [c for c in pool if c.cleaned_at == newest] if with_ts else pool
        return min(candidates, key=lambda c: c.record_id)
    if strategy == "most_complete":
        best = max(c.completeness for c in contribs)
        return min((c for c in contribs if c.completeness == best),
                   key=lambda c: c.record_id)
    # most_frequent: modal value; ties fall to source_priority, then record_id
    counts = Counter(repr(c.value) for c in contribs)
    top = max(counts.values())
    modal = [c for c in contribs if counts[repr(c.value)] == top]
    return min(modal, key=lambda c: (_source_rank(c, policy.source_priority),
                                     c.record_id))


def resolve_attribute(
    attribute: str,
    contributions: list[Contribution],
    policy: SurvivorshipPolicy,
) -> tuple[Contribution, dict[str, Any] | None]:
    """Pick the surviving contribution for one attribute; report any conflict.

    Args:
        attribute: Attribute name.
        contributions: Non-empty candidate values with metadata.
        policy: Effective survivorship policy.

    Returns:
        (winning_contribution, conflict_row_or_None). The conflict row carries
        the losing values with their source/record provenance for the audit.
    """
    strategy = policy.strategy_for(attribute)
    winner = _pick(contributions, strategy, policy)
    distinct = {repr(c.value) for c in contributions}
    conflict = None
    if len(distinct) > 1:
        conflict = {
            "attribute": attribute,
            "winning_value": winner.value,
            "losing_values": [
                {"value": c.value, "source_system": c.source_system,
                 "record_id": c.record_id}
                for c in contributions if repr(c.value) != repr(winner.value)
            ],
            "strategy": strategy,
        }
    return winner, conflict
