"""Load SQL from .sql files — keeps SQL out of Python (DB-Guard discipline)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SQL_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def load(name: str) -> str:
    """Return the SQL text for a named query file (without the .sql suffix).

    Args:
        name: Query file stem, e.g. 'insert_run'.

    Returns:
        The file's SQL text, stripped.
    """
    return (_SQL_DIR / f"{name}.sql").read_text(encoding="utf-8").strip()
