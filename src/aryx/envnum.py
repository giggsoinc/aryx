"""Numeric settings read from the environment, tolerant of a typo."""
from __future__ import annotations

import logging
import os
from collections.abc import Callable

logger = logging.getLogger(__name__)


def env_number(name: str, default: float, cast: Callable[[str], float] = float,
               minimum: float | None = None) -> float:
    """``cast(os.environ[name])``, or ``default`` when unset, malformed or below ``minimum``.

    A setting read at import time must never stop the module from importing:
    ``ARYX_EXTRACT_WORKERS=three`` logs a warning and uses the default.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = cast(raw.strip())
    except (TypeError, ValueError):
        logger.warning("ignoring %s=%r (not a number); using %s", name, raw, default)
        return default
    if minimum is not None and value < minimum:
        logger.warning("ignoring %s=%r (below %s); using %s", name, raw, minimum, default)
        return default
    return value
