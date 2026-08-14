"""User Intent Capture pipeline (C01) — deterministic, no LLM.

Mirrors the component Procedure:
  1. (form renders required + optional fields — UI concern)
  2. require a non-empty domain and objective
  3. normalize whitespace, dates, and list fields
  4. validate values against UI catalogues (unsupported -> warning, retained)
  5. build a versioned user_intent object
  6. attach a correlation id (ready for handoff to the next component)

Missing required fields BLOCK (validation_status="invalid", field-level errors);
inconsistent dates block; unsupported catalogue values WARN but are retained.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from aryx.intent.catalogues import AUDIENCES, CHART_TYPES
from aryx.intent.models import (
    DateRange,
    IntentPreferences,
    UserIntent,
    UserIntentRequest,
)

logger = logging.getLogger(__name__)

# Blocking inputs — an empty value on any of these makes the request incomplete.
REQUIRED_FIELDS = ("uploaded_file", "domain", "objective")

_WS = re.compile(r"\s+")
# Accepted input date formats; all normalize to ISO YYYY-MM-DD.
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y")


def _norm_text(value: str) -> str:
    """Strip ends and collapse internal whitespace runs to single spaces."""
    return _WS.sub(" ", (value or "").strip())


def _norm_list(values: list[str]) -> list[str]:
    """Normalize each item, drop blanks, dedupe case-insensitively (order kept)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        item = _norm_text(raw)
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _norm_date(value: str) -> tuple[str, bool]:
    """Parse a date to ISO `YYYY-MM-DD`. Empty is valid; returns (iso, ok)."""
    text = _norm_text(value)
    if not text:
        return "", True
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat(), True
        except ValueError:
            continue
    try:  # last resort: ISO 8601 with time component
        return datetime.fromisoformat(text).date().isoformat(), True
    except ValueError:
        return text, False


def _new_request_id() -> str:
    """Generate a correlation id, e.g. `req_1a2b3c4d5e6f`."""
    return f"req_{uuid.uuid4().hex[:12]}"


def capture_intent(
    request: UserIntentRequest,
    *,
    request_id: str | None = None,
    chart_types: frozenset[str] = CHART_TYPES,
    audiences: frozenset[str] = AUDIENCES,
) -> UserIntent:
    """Validate, normalize, and version a capture request.

    Args:
        request: Raw form input.
        request_id: Explicit correlation id; falls back to `request.request_id`,
            then to a generated one.
        chart_types: Chart-type catalogue (lowercase) to validate against.
        audiences: Audience catalogue (lowercase) to validate against.

    Returns:
        A versioned UserIntent. `validation_status` is "invalid" when `errors`
        is non-empty; unsupported preferences appear in `warnings` but are kept.
    """
    # Step 3 — normalize.
    uploaded_file = _norm_text(request.uploaded_file)
    domain = _norm_text(request.domain)
    objective = _norm_text(request.objective)
    audience = _norm_text(request.target_audience)
    kpis = _norm_list(request.preferred_kpis)
    dimensions = _norm_list(request.preferred_dimensions)
    charts = _norm_list(request.preferred_chart_types)

    errors: list[str] = []
    warnings: list[str] = []

    # Step 2 — required fields.
    for name, value in (
        ("uploaded_file", uploaded_file),
        ("domain", domain),
        ("objective", objective),
    ):
        if not value:
            errors.append(f"{name} is required")

    # Step 3 (cont.) — dates. Optional; inconsistent/unparseable dates block.
    date_range: DateRange | None = None
    if request.date_range is not None:
        start, start_ok = _norm_date(request.date_range.start)
        end, end_ok = _norm_date(request.date_range.end)
        if not start_ok:
            errors.append(f"date_range.start is not a valid date: {request.date_range.start!r}")
        if not end_ok:
            errors.append(f"date_range.end is not a valid date: {request.date_range.end!r}")
        if start_ok and end_ok and start and end and start > end:
            errors.append(f"date_range start {start} is after end {end}")
        date_range = DateRange(start=start, end=end)

    # Step 4 — catalogue validation (chart types + audience). Retain + warn.
    for chart in charts:
        if chart.lower() not in chart_types:
            warnings.append(f"unsupported chart type: {chart!r}")
    if audience and audience.lower() not in audiences:
        warnings.append(f"unsupported target audience: {audience!r}")

    status = "invalid" if errors else "valid"

    # Steps 5 + 6 — versioned object + correlation id.
    resolved_id = _norm_text(request_id or request.request_id) or _new_request_id()

    intent = UserIntent(
        request_id=resolved_id,
        uploaded_file=uploaded_file,
        domain=domain,
        objective=objective,
        preferences=IntentPreferences(
            preferred_kpis=kpis,
            preferred_dimensions=dimensions,
            preferred_chart_types=charts,
            target_audience=audience,
            date_range=date_range,
        ),
        validation_status=status,
        warnings=warnings,
        errors=errors,
    )
    logger.info(
        "captured intent request_id=%s status=%s warnings=%d errors=%d",
        intent.request_id, status, len(warnings), len(errors),
    )
    return intent
