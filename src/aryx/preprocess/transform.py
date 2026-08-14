"""Per-column deterministic conversion + the soft per-column safety gate (C10).

Never mutates the raw snapshot — operates on an in-memory copy of parsed row
values. Mirrors the component Procedure's steps 2-7: standardize null tokens,
convert by policy, clean category labels without arbitrary reordering, apply
explicit null rules, and never auto-normalize beyond what's requested.

THRESHOLD is an engineering default (not a spec'd number, flagged as such in
the C10 plan): a column whose conversion failure rate exceeds it reverts to
its original (null-standardized) values and is marked `reverted=True` — it
never blocks the rest of the dataset (step 9's "PASS ALL CONTROLS?" gate is
soft: "NO -> retain original and warn", never a hard stop).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

THRESHOLD = 0.10  # 10% failed rows -> revert this column to original + warn

_NULL_TOKENS = {"", "null", "none", "n/a", "na", "nan", "-"}
_BOOL_TRUE = {"true", "yes", "y", "1", "t"}
_BOOL_FALSE = {"false", "no", "n", "0", "f"}
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S")


def _std_null(value: Any) -> str | None:
    """Step 2: trim whitespace, standardize null tokens to None."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in _NULL_TOKENS else text


def _to_numeric(text: str) -> float | None:
    cleaned = text.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_date(text: str) -> str | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _to_boolean(text: str) -> bool | None:
    low = text.strip().lower()
    if low in _BOOL_TRUE:
        return True
    if low in _BOOL_FALSE:
        return False
    return None


_CONVERTERS: dict[str, Callable[[str], Any]] = {
    "numeric_conversion": _to_numeric,
    "date_conversion": _to_date,
    "boolean_conversion": _to_boolean,
}


def convert_column(values: list[Any], operation: str) -> tuple[list[Any], int, int, bool]:
    """Convert one column's raw values per `operation`.

    Returns (converted_values, failed_rows, changed_rows, reverted).
    `changed_rows` counts non-null values actually altered by the operation —
    not just "seen". `reverted=True` means failed_rows exceeded THRESHOLD and
    `converted_values` is the ORIGINAL (null-standardized) values, unconverted.
    """
    std = [_std_null(v) for v in values]

    if operation == "trim_whitespace":
        changed = sum(1 for raw, s in zip(values, std)
                     if raw is not None and s is not None and str(raw) != s)
        return std, 0, changed, False

    if operation == "trim_and_normalize_category":
        # Step 4: clean labels, no arbitrary reordering — same values, just
        # whitespace-trimmed, in their original encounter order.
        changed = sum(1 for raw, s in zip(values, std)
                     if raw is not None and s is not None and str(raw) != s)
        return std, 0, changed, False

    converter = _CONVERTERS.get(operation)
    if converter is None:
        return std, 0, 0, False

    non_null = [s for s in std if s is not None]
    converted: list[Any] = []
    failed = 0
    changed = 0
    for raw, s in zip(values, std):
        if s is None:
            converted.append(None)
            continue
        result = converter(s)
        if result is None:
            failed += 1
            converted.append(None)
            continue
        converted.append(result)
        # "Changed" means the operation actually repaired something in the
        # text, not merely that the output's Python type reprs differently
        # from the input string (e.g. "100" -> 100.0 must NOT count — it's
        # the same value, just typed; str(100.0) != "100" would wrongly flag
        # every clean numeric row as changed).
        if operation == "numeric_conversion":
            cleaned = s.replace(",", "").replace("$", "").replace("%", "").strip()
            if cleaned != s:
                changed += 1
        elif operation == "date_conversion":
            if s != str(result):
                changed += 1
        # boolean_conversion: encoding "yes"/"1"/etc. to a Python bool is a
        # type mapping, not a content repair — never counted as changed.

    if non_null and (failed / len(non_null)) > THRESHOLD:
        return std, failed, 0, True  # unsafe: revert this column, keep original

    return converted, failed, changed, False
