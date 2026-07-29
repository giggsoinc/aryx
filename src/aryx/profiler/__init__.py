"""Deterministic Dataset Profiler (C03).

Reads an immutable dataset snapshot (from C02) and measures file-, table-, and
column-level structure, quality, types, distributions, and analytical roles —
producing a versioned dataset_profile that is the authoritative source of real
column names, canonical types, and quality conditions for everything downstream.
No LLM.
"""

from aryx.profiler.models import ColumnProfile, DatasetProfile, QualityFlag
from aryx.profiler.profile import profile_dataset

__all__ = ["profile_dataset", "DatasetProfile", "ColumnProfile", "QualityFlag"]
