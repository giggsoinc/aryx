"""Deterministic column/table profiling (C03) — stdlib only, no LLM.

Mirrors the component Procedure:
  1. load data with explicit UTF-8 decoding
  2. count rows, columns, duplicates, empty rows
  3. per column: retain original type + infer canonical type
  4. compute nulls, uniqueness, examples, min/max/mean/median, category freqs
  5. detect constants, high cardinality, identifier-like, mixed types, outliers
  6. assign evidence-based analytical roles
  7. record limitations + profile version
  8. (caller) validate + persist

Type inference is evidence-based and order-sensitive: a column is only given a
canonical type its non-null values actually support.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
from typing import Any

from aryx.connectors.json_source import _flatten
from aryx.profiler.models import (
    ColumnProfile,
    DatasetProfile,
    QualityFlag,
)

_SAMPLE_N = 5
_TOP_CATEGORIES_N = 10
_CATEGORICAL_MAX = 50           # distinct ceiling for a categorical column
_HIGH_CARD_RATIO = 0.9          # unique/non-null above this on text = high cardinality
_ID_NAME = re.compile(r"(^|_)(id|key|code|uuid|guid|number|no)$", re.IGNORECASE)
_STATUS_NAME = re.compile(r"(status|state|stage|flag|type|category)", re.IGNORECASE)
_BOOL_TRUE = {"true", "yes", "y", "1", "t"}
_BOOL_FALSE = {"false", "no", "n", "0", "f"}
_STATUS_VOCAB = {
    "renewed", "not renewed", "pending", "active", "inactive", "open", "closed",
    "approved", "rejected", "complete", "completed", "cancelled", "canceled",
    "new", "in progress", "done", "failed", "success", "won", "lost", "expired",
}
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S")
# A real decimal number: optional sign, digits/decimal, optional exponent.
# Deliberately excludes 'nan', 'inf', and underscore-grouped literals.
_NUMERIC_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _load(data: bytes, fmt: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (rows, column_order). CSV values are strings; JSON are flattened."""
    if fmt == "json":
        loaded = json.loads(data.decode("utf-8"))
        raw = loaded if isinstance(loaded, list) else [loaded]
        rows = [_flatten(r) if isinstance(r, dict) else {"value": r} for r in raw]
    else:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8", "ignore")))
        rows = [dict(r) for r in reader]
    order: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for col in row:
            if col is not None and col not in seen:
                seen.add(col)
                order.append(col)
    return rows, order


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _as_number(value: Any) -> float | None:
    """Parse a finite decimal number, or None.

    Rejects Python float() quirks that are not real data numbers — 'NaN',
    'Infinity', and underscore-grouped literals like '1_000' — because
    non-finite values later fail Postgres jsonb serialization.
    """
    text = str(value).replace(",", "").strip()
    if not _NUMERIC_RE.match(text):
        return None
    try:
        num = float(text)
    except (ValueError, TypeError):
        return None
    return num if math.isfinite(num) else None


def _is_date(value: Any) -> bool:
    from datetime import datetime
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def _original_type(values: list[Any]) -> str:
    for v in values:
        if not _is_blank(v):
            return type(v).__name__ if not isinstance(v, str) else "string"
    return "string"


def _profile_column(name: str, values: list[Any], row_count: int
                    ) -> tuple[ColumnProfile, list[QualityFlag]]:
    non_null = [v for v in values if not _is_blank(v)]
    null_count = row_count - len(non_null)
    as_str = [str(v).strip() for v in non_null]
    distinct = sorted(set(as_str))
    unique_count = len(distinct)
    flags: list[QualityFlag] = []

    numbers = [n for n in (_as_number(v) for v in non_null) if n is not None]
    numeric_frac = (len(numbers) / len(non_null)) if non_null else 0.0
    is_numeric = non_null and numeric_frac == 1.0
    is_bool = bool(non_null) and all(s.lower() in _BOOL_TRUE | _BOOL_FALSE for s in as_str)
    is_date = bool(non_null) and all(_is_date(v) for v in non_null)
    # Distinct across non-null values — a real id column keeps identifier status
    # even with a stray null (don't require unique_count == row_count).
    all_distinct = bool(non_null) and unique_count == len(non_null)

    # ── canonical type (evidence-based, order matters) ──
    if not non_null:
        canonical = "empty"
    elif is_bool and unique_count <= 2:
        canonical = "boolean"
    elif all_distinct and (bool(_ID_NAME.search(name)) or _looks_like_code(as_str)):
        canonical = "identifier"
    elif is_numeric:
        canonical = "numeric"
    elif is_date:
        canonical = "datetime"
    elif unique_count <= _CATEGORICAL_MAX and unique_count < len(non_null):
        canonical = "categorical"
    else:
        canonical = "text"

    # ── analytical role ──
    role: str
    if canonical == "identifier":
        role = "identifier"
    elif canonical == "numeric":
        role = "measure"
    elif canonical == "datetime":
        role = "time"
    elif canonical in ("categorical", "boolean"):
        statusy = bool(_STATUS_NAME.search(name)) or (
            unique_count <= 6 and all(s.lower() in _STATUS_VOCAB for s in distinct)
        )
        role = "status" if statusy else "dimension"
    else:
        role = "attribute"

    prof = ColumnProfile(
        name=name, original_type=_original_type(non_null), canonical_type=canonical,
        null_count=null_count, unique_count=unique_count,
        sample_values=distinct[:_SAMPLE_N], candidate_role=role,
    )
    if canonical == "numeric" and numbers:
        prof.min = min(numbers)
        prof.max = max(numbers)
        prof.mean = round(statistics.fmean(numbers), 4)
        prof.median = statistics.median(numbers)
    if canonical in ("categorical", "boolean"):
        counts: dict[str, int] = {}
        for s in as_str:
            counts[s] = counts.get(s, 0) + 1
        prof.top_categories = [
            {"value": v, "count": c}
            for v, c in sorted(counts.items(), key=lambda kv: -kv[1])[:_TOP_CATEGORIES_N]
        ]

    # ── quality flags (step 5) ──
    if null_count > 0:
        flags.append(QualityFlag(column=name, code="missing_values", count=null_count))
    if non_null and unique_count == 1:
        flags.append(QualityFlag(column=name, code="constant", count=len(non_null),
                                 detail=f"single value: {distinct[0]!r}"))
    if canonical == "text" and non_null and unique_count / len(non_null) >= _HIGH_CARD_RATIO:
        flags.append(QualityFlag(column=name, code="high_cardinality", count=unique_count))
    if non_null and 0.0 < numeric_frac < 1.0 and canonical not in ("identifier",):
        flags.append(QualityFlag(column=name, code="mixed_types",
                                 count=len(numbers),
                                 detail=f"{numeric_frac:.0%} of values are numeric"))
    if canonical == "numeric" and len(numbers) > 3:
        outliers = _outliers(numbers)
        if outliers:
            flags.append(QualityFlag(column=name, code="outliers", count=outliers))
    return prof, flags


def _looks_like_code(values: list[str]) -> bool:
    """Alphanumeric codes (e.g. 'C001', 'AB-12') — must contain a letter, so a
    purely numeric all-distinct column is treated as a measure, not an id."""
    sample = values[:50]
    if not sample:
        return False
    tokenish = all(re.fullmatch(r"[A-Za-z0-9][\w\-]*", s or "") for s in sample)
    has_letter = any(re.search(r"[A-Za-z]", s or "") for s in sample)
    return tokenish and has_letter


def _outliers(numbers: list[float]) -> int:
    """Count values beyond mean ± 3σ (population)."""
    if len(numbers) < 4:
        return 0
    mean = statistics.fmean(numbers)
    sd = statistics.pstdev(numbers)
    if sd == 0:
        return 0
    return sum(1 for n in numbers if abs(n - mean) > 3 * sd)


def profile_dataset(data: bytes, fmt: str, dataset_id: str, version: str
                    ) -> DatasetProfile:
    """Profile an immutable snapshot into a versioned DatasetProfile."""
    rows, order = _load(data, fmt)
    row_count = len(rows)

    empty_rows = sum(1 for r in rows if all(_is_blank(v) for v in r.values()))
    seen_rows: set[str] = set()
    duplicates = 0
    for r in rows:
        key = json.dumps({k: r.get(k) for k in order}, sort_keys=True, default=str)
        if key in seen_rows:
            duplicates += 1
        else:
            seen_rows.add(key)

    columns: list[ColumnProfile] = []
    flags: list[QualityFlag] = []
    for col in order:
        prof, col_flags = _profile_column(col, [r.get(col) for r in rows], row_count)
        columns.append(prof)
        flags.extend(col_flags)

    limitations: list[str] = []
    if fmt == "json":
        limitations.append("JSON columns are flattened with dot-notation before profiling.")
    if row_count == 0:
        limitations.append("Empty dataset — no column statistics computed.")

    return DatasetProfile(
        dataset_profile_id=f"profile_{dataset_id}_{version}",
        dataset_id=dataset_id, dataset_version=version,
        row_count=row_count, column_count=len(order),
        duplicate_row_count=duplicates, empty_row_count=empty_rows,
        columns=columns, quality_flags=flags, limitations=limitations,
        profile_status="valid" if order else "invalid",
    )
