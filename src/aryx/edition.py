"""Aryx edition flag — Lite (v1, OSS) vs Enterprise (v2) vs Aryx-o (v2.1).

The edition is read once from ``ARYX_EDITION`` (default ``lite``). It gates
Enterprise-only surfaces (the Accuracy Lab, governance, the LLM Router) and
selects the default adapter family. Aryx-o is Enterprise with the Oracle
adapter set — same engine, different substrate (see docs/EDITIONS.md).
"""
from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache


class Edition(str, Enum):
    """The shipped editions, in capability order."""

    LITE = "lite"
    ENTERPRISE = "enterprise"
    ARYX_O = "aryx-o"

    @property
    def is_enterprise(self) -> bool:
        """True for Enterprise and Aryx-o (both unlock v2 surfaces)."""
        return self in (Edition.ENTERPRISE, Edition.ARYX_O)


@lru_cache(maxsize=1)
def current_edition() -> Edition:
    """Return the active edition from ARYX_EDITION (default: lite)."""
    raw = os.getenv("ARYX_EDITION", "lite").strip().lower()
    try:
        return Edition(raw)
    except ValueError:
        return Edition.LITE
