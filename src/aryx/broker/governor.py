"""Token governor: per-tier budgets with downgrade-on-overflow (P6)."""
from __future__ import annotations

import logging

from aryx.broker.specs import TIER_LADDER, Tier

logger = logging.getLogger(__name__)


class TokenGovernor:
    """Tracks token spend per tier and downgrades when a budget is exhausted."""

    def __init__(self, budgets: dict[str, int]) -> None:
        """Configure per-tier token budgets (0 or missing means unlimited)."""
        self._budgets = budgets
        self._spent: dict[str, int] = {}

    def charge(self, tier: Tier, tokens: int) -> None:
        """Record token spend against a tier."""
        self._spent[tier] = self._spent.get(tier, 0) + tokens

    def _exhausted(self, tier: Tier) -> bool:
        """True when a tier has a positive budget and has spent beyond it."""
        budget = self._budgets.get(tier, 0)
        return budget > 0 and self._spent.get(tier, 0) >= budget

    def effective_tier(self, requested: Tier) -> Tier:
        """Return the requested tier, or the next cheaper one if over budget."""
        ladder = TIER_LADDER[TIER_LADDER.index(requested):]
        for tier in ladder:
            if not self._exhausted(tier):
                return tier
        logger.warning("all tiers from %s exhausted; using %s", requested, ladder[-1])
        return ladder[-1]
