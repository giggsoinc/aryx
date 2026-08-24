"""Detect identifier-shaped columns from their sampled values (G-blocking-fix).

Structured ids (EMP101, TK103, CO101, ORD-4821) are useless — often actively
misleading — as entity-resolution match text: they're unique by construction,
so a "most unique column" heuristic reaches for them first, and a shared
prefix/format across unrelated records (e.g. everyone's employee_id starting
"EMP1") then collides in blocking and inflates string-similarity scores. This
is name-blind by design — with real datasets running to hundreds of columns,
a hardcoded field-name list (employee_id, ticket_id, ...) can't scale, but a
statistical check of what the *values* look like does.

The fallback picks MULTIPLE columns, not the single most-unique one: an
earlier version collapsed to one column and broke Order records, where
`company_name` alone is a shared foreign-key-like reference across many
legitimately-different orders — comparing on that one field alone turned
"are these the same order?" into "do they mention the same company?". Using
several non-identifier columns together keeps the other distinguishing
fields (order_status, product_name) in play, the same way a well-formed
multi-key proposal already would.
"""
from __future__ import annotations

import re

_ID_SHAPE = re.compile(r"^[A-Za-z]{1,6}[-_]?\d{2,}[A-Za-z0-9]*$")
# Prefix requires >=1 letter: a bare digit run ("34", "42") is a plain
# numeric value (age, year, quantity), not a structured code — allowing
# zero letters let is_row_identifier misclassify a small, momentarily
# all-distinct sample of an ordinary numeric column as transactional,
# silently skipping entity resolution for the whole type (DEC-011).


def is_identifier_like(values: list[str], min_samples: int = 2,
                       uniqueness_threshold: float = 0.9) -> bool:
    """True when a column's sampled values look like a structured code.

    Requires both near-total uniqueness (ids don't repeat) and a majority
    code-shaped pattern (short letter prefix + digit run) among the distinct
    values — free text (names, emails, descriptions) satisfies neither.
    Too few samples to judge (`min_samples`) returns False rather than
    guessing.
    """
    cleaned = [v.strip() for v in values if v and v.strip()]
    if len(cleaned) < min_samples:
        return False
    distinct = set(cleaned)
    if len(distinct) / len(cleaned) < uniqueness_threshold:
        return False
    code_shaped = sum(1 for v in distinct if _ID_SHAPE.match(v))
    return code_shaped / len(distinct) >= 0.8


def is_row_identifier(values: list[str], min_samples: int = 2) -> bool:
    """True only when a column is unmistakably a per-row identifier.

    Deliberately stricter than ``is_identifier_like`` (which allows 90%
    uniqueness, tolerating an occasional repeat): this requires every
    sampled value to be distinct, with no exceptions, on top of the same
    code-shaped check. This is the narrow signal used to skip entity
    resolution entirely for a whole ontology type (a genuine Order/Ticket/
    Event key) — getting it wrong misclassifies a real dimension type
    (Company, Employee) as transactional, so it must never fire on
    coincidental 100%-uniqueness in a small sample alone; the code-shape
    requirement is what keeps it from doing that.
    """
    cleaned = [v.strip() for v in values if v and v.strip()]
    if len(cleaned) < min_samples:
        return False
    distinct = set(cleaned)
    if len(distinct) != len(cleaned):
        return False
    code_shaped = sum(1 for v in distinct if _ID_SHAPE.match(v))
    return code_shaped / len(distinct) >= 0.8


def best_match_columns(colvals: dict[str, list[str]], columns: list[str],
                       cap: int = 3) -> list[str]:
    """Natural-key columns for the whole-row repair fallback.

    Ranks every column by (non-identifier-shaped first, then uniqueness
    descending) and returns the top `cap` — several columns together, not
    just one, so no single shared value (a company name repeated across
    orders, a department shared by employees) becomes the *entire* basis
    for comparison. Only reaches into identifier-shaped columns if nothing
    else is available at all — still better than refusing to pick anything.
    """
    def uniqueness(col: str) -> int:
        """Count of distinct non-empty sampled values for one column."""
        return len({v for v in colvals.get(col, []) if v})

    free_text = sorted((c for c in columns if not is_identifier_like(colvals.get(c, []))),
                       key=uniqueness, reverse=True)
    if free_text:
        return free_text[:cap]
    return [max(columns, key=uniqueness)]


def resolve_match_keys(
    proposed_keys: list[str], colvals: dict[str, list[str]],
) -> tuple[list[str], bool]:
    """Decide the real match keys for one file, and whether its type is
    transactional (skip entity resolution entirely for it).

    Extracted from the ingest match-key repair step so the decision itself —
    not just its building blocks — is independently testable. Three
    outcomes, in priority order:

    1. Exactly one proposed key, and it's a genuine per-row identifier
       (``is_row_identifier``) — transactional; keep that key for
       provenance/display, but the caller must skip resolution entirely.
    2. Otherwise, drop any identifier-shaped columns from what was
       validly proposed; if something free-text remains, use it as-is.
    3. Nothing usable was proposed (or everything proposed was
       identifier-shaped) — pick real natural keys from every column in
       the file (``best_match_columns``). If the file has no columns at
       all, the original proposal is returned unchanged.

    Returns:
        (keys, skip_resolution).
    """
    cols = list(colvals.keys())
    valid = [k for k in proposed_keys if k in cols]
    if len(valid) == 1 and is_row_identifier(colvals.get(valid[0], [])):
        return valid, True
    free_text_valid = [k for k in valid if not is_identifier_like(colvals.get(k, []))]
    if free_text_valid:
        return free_text_valid, False
    if cols:
        return best_match_columns(colvals, cols), False
    return proposed_keys, False
