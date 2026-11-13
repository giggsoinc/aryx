"""Exact facts for the Ask flow: real counts, record details, value breakdowns.

Ask used to describe a workspace from the first 500 entities and to show the
model only a record's name and links. That made "how many contracts?" wrong
past 500 entities and "what is ticket T-5's status?" unanswerable. This module
supplies the missing facts straight from the database and formats them as
compact text for the model.

Two rules shape it:

* **Fail soft, visibly.** Every fetcher keeps Ask answering (with less detail)
  when a swapped-in graph adapter lacks these methods or a query fails. Each
  fallback is logged once per adapter, not once per question.
* **Field values reach the answer model**, which can be a hosted provider.
  ``ARYX_ASK_ATTRIBUTES`` controls that: ``off`` sends none, ``safe`` (default)
  drops obviously sensitive keys and values, ``all`` sends everything.
"""
from __future__ import annotations

import re
import threading
from collections import Counter
from typing import Any

from aryx.raven_log_config import log as raven_log

_SERVICE = "aryx-api"
_SAMPLE_LIMIT = 500        # the old, capped sample — now only a fallback
MAX_ATTRIBUTES = 12        # attributes shown per record
MAX_VALUE_CHARS = 80       # longest attribute value shown
MAX_NEIGHBORS = 25         # linked records listed per entity
MAX_BREAKDOWN_KEYS = 6     # categorical attributes shown per type
MAX_BREAKDOWN_VALUES = 8   # distinct values counted per attribute
_DEFAULT_BREAKDOWN_LIMIT = 50_000   # workspace size above which value counts are skipped

# Keys shown first when a type has more categorical keys than we can list:
# the ones people actually ask "how many ...?" about.
_PREFERRED_KEYS = ("status", "state", "stage", "priority", "severity",
                   "type", "category", "tier")

# Tokens of an attribute name that mark it as sensitive in "safe" mode.
_SENSITIVE_TOKENS = frozenset({
    "email", "mail", "phone", "mobile", "fax", "ssn", "passport", "password",
    "passwd", "secret", "token", "credential", "credentials", "apikey", "dob",
    "birth", "birthday", "birthdate", "address", "street", "zip", "postal",
    "postcode", "card", "iban", "swift", "routing", "salary", "wage", "tin",
    "license", "licence", "pin", "otp"})
_SENSITIVE_COMPOUNDS = ("apikey", "accountnumber", "creditcard", "taxid",
                        "socialsecurity", "bankaccount")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

_logged: set[tuple[str, str]] = set()
_logged_lock = threading.Lock()


def _first_time(code: str, subject: str) -> bool:
    """True the first time ``(code, subject)`` is seen in this process.

    Fallback logs are rate limited to once per adapter and code, so a missing
    method does not log a WARN on every single question.
    """
    key = (code, subject)
    with _logged_lock:
        if key in _logged:
            return False
        _logged.add(key)
        return True


def _fallback_context(subject: str, workspace_id: int | None, code: str,
                      reason: str) -> dict[str, Any]:
    """The raven-log context for an Ask fallback."""
    return {"object_id": subject, "workspace_id": workspace_id,
            "final_status": "degraded", "result": "fallback",
            "reason_code": code, "stage": "Ask", "detail": reason[:200]}


def attributes_mode() -> str:
    """Return ``off``, ``safe`` or ``all`` (``ARYX_ASK_ATTRIBUTES``; default ``safe``)."""
    try:
        from aryx.config import get_settings
        mode = str(get_settings().ask_attributes)
    except Exception as exc:  # noqa: BLE001 — never let config break Ask
        if _first_time("ASK_ATTRIBUTES_MODE_DEFAULTED", "config"):
            raven_log(
                "WARN", "could not read ARYX_ASK_ATTRIBUTES; using 'safe'",
                criticality="P3", service=_SERVICE,
                error_code="ASK_ATTRIBUTES_MODE_DEFAULTED",
                context=_fallback_context("config", None,
                                          "ASK_ATTRIBUTES_MODE_DEFAULTED", str(exc)))
        return "safe"
    return mode if mode in ("off", "safe", "all") else "safe"


def breakdown_limit() -> int:
    """Largest workspace (entities) that gets value counts (``ARYX_ASK_BREAKDOWN_MAX_ENTITIES``)."""
    try:
        from aryx.config import get_settings
        return int(get_settings().ask_breakdown_max_entities)
    except Exception as exc:  # noqa: BLE001 — never let config break Ask
        if _first_time("ASK_BREAKDOWN_LIMIT_DEFAULTED", "config"):
            raven_log(
                "WARN", "could not read ARYX_ASK_BREAKDOWN_MAX_ENTITIES; using the default",
                criticality="P4", service=_SERVICE,
                error_code="ASK_BREAKDOWN_LIMIT_DEFAULTED",
                context=_fallback_context("config", None,
                                          "ASK_BREAKDOWN_LIMIT_DEFAULTED", str(exc)))
        return _DEFAULT_BREAKDOWN_LIMIT


def is_sensitive_key(key: str) -> bool:
    """True when an attribute name looks like personal or secret data."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key))
    tokens = [t for t in re.split(r"[^a-z0-9]+", spaced.lower()) if t]
    if any(t in _SENSITIVE_TOKENS for t in tokens):
        return True
    joined = "".join(tokens)
    return any(c in joined for c in _SENSITIVE_COMPOUNDS)


def _is_sensitive_value(value: Any) -> bool:
    """True for an email address or a long digit run (phone, card, id number)."""
    if isinstance(value, (dict, list)) or value is None:
        return False
    text = str(value)
    if _EMAIL.search(text):
        return True
    digits = re.sub(r"[\s().+-]", "", text)
    return digits.isdigit() and len(digits) >= 9


def _scrub(attrs: dict[str, Any], mode: str) -> dict[str, Any]:
    """Apply the privacy mode to one record's attributes."""
    if mode == "off":
        return {}
    if mode == "all":
        return attrs
    return {k: v for k, v in attrs.items()
            if not is_sensitive_key(k) and not _is_sensitive_value(v)}


def type_counts(reader: Any, workspace_id: int | None = None) -> tuple[dict[str, int], bool]:
    """Return ``({ontology_type: count}, exact)`` for the workspace.

    ``exact`` is True when the counts come from a real ``COUNT`` query. When
    the adapter has no ``count_by_type`` (or it fails) the counts come from the
    old 500-row sample and ``exact`` is False, so callers can say "at least".
    """
    subject = type(reader).__name__
    fn = getattr(reader, "count_by_type", None)
    if fn is not None:
        try:
            return {str(k): int(v) for k, v in fn().items()}, True
        except Exception as exc:  # noqa: BLE001 — fall back, never break Ask
            if _first_time("ASK_COUNTS_APPROXIMATE", subject):
                raven_log(
                    "WARN", "type counts query failed; using a sampled count",
                    criticality="P3", service=_SERVICE,
                    error_code="ASK_COUNTS_APPROXIMATE",
                    context=_fallback_context(subject, workspace_id,
                                              "ASK_COUNTS_APPROXIMATE", str(exc)))
    elif _first_time("ASK_COUNTS_APPROXIMATE", subject):
        raven_log(
            "WARN", "graph adapter has no count_by_type; using a sampled count",
            criticality="P3", service=_SERVICE, error_code="ASK_COUNTS_APPROXIMATE",
            context=_fallback_context(subject, workspace_id,
                                      "ASK_COUNTS_APPROXIMATE", "missing count_by_type"))
    sample = Counter(str(e.get("type", "?"))
                     for e in reader.find_entities(limit=_SAMPLE_LIMIT))
    return dict(sample), False


def sample_names(reader: Any, types: list[str],
                 workspace_id: int | None = None, per_type: int = 3) -> dict[str, list[str]]:
    """Return a few display names per type — one query when the adapter has it."""
    fn = getattr(reader, "sample_names", None)
    if fn is not None:
        try:
            return fn(per_type)
        except Exception as exc:  # noqa: BLE001 — fall back to one query per type
            subject = type(reader).__name__
            if _first_time("ASK_SAMPLES_PER_TYPE", subject):
                raven_log(
                    "WARN", "sample-names query failed; querying type by type",
                    criticality="P3", service=_SERVICE,
                    error_code="ASK_SAMPLES_PER_TYPE",
                    context=_fallback_context(subject, workspace_id,
                                              "ASK_SAMPLES_PER_TYPE", str(exc)))
    return {t: [n for n in (e.get("name", "") for e in
                            reader.find_entities(ontology_type=t, limit=per_type)) if n]
            for t in types}


def attribute_breakdown(reader: Any, workspace_id: int | None = None,
                        total_entities: int | None = None
                        ) -> dict[str, dict[str, dict[str, int]]]:
    """Return ``{type: {attribute: {value: count}}}`` or ``{}`` if unavailable, off or too big.

    The pass reads every attribute of every entity, so it is skipped (with one
    log line) when ``total_entities`` exceeds ``ARYX_ASK_BREAKDOWN_MAX_ENTITIES``.
    """
    mode = attributes_mode()
    fn = getattr(reader, "attribute_breakdown", None)
    if mode == "off" or fn is None:
        return {}
    limit = breakdown_limit()
    if limit and total_entities is not None and total_entities > limit:
        if _first_time("ASK_BREAKDOWN_SKIPPED", f"workspace-{workspace_id}"):
            raven_log(
                "INFO", "workspace too large for value counts; overview has counts only",
                criticality="P4", service=_SERVICE, error_code="ASK_BREAKDOWN_SKIPPED",
                context=_fallback_context(
                    f"workspace-{workspace_id}", workspace_id, "ASK_BREAKDOWN_SKIPPED",
                    f"{total_entities} entities > ARYX_ASK_BREAKDOWN_MAX_ENTITIES={limit}"))
        return {}
    try:
        raw = fn(MAX_BREAKDOWN_VALUES)
    except Exception as exc:  # noqa: BLE001 — breakdown is a nice-to-have
        subject = type(reader).__name__
        if _first_time("ASK_BREAKDOWN_UNAVAILABLE", subject):
            raven_log(
                "WARN", "attribute breakdown query failed; overview has counts only",
                criticality="P3", service=_SERVICE,
                error_code="ASK_BREAKDOWN_UNAVAILABLE",
                context=_fallback_context(subject, workspace_id,
                                          "ASK_BREAKDOWN_UNAVAILABLE", str(exc)))
        return {}
    if mode == "all":
        return raw
    safe: dict[str, dict[str, dict[str, int]]] = {}
    for kind, by_key in raw.items():
        for key, values in by_key.items():
            if is_sensitive_key(key):
                continue
            kept = {v: n for v, n in values.items() if not _is_sensitive_value(v)}
            if kept:
                safe.setdefault(kind, {})[key] = kept
    return safe


def entity_attributes(reader: Any, entities: list[Any],
                      workspace_id: int | None = None) -> dict[int, dict[str, Any]]:
    """Return ``{entity_id: attributes}`` for the retrieved entities, or ``{}``."""
    mode = attributes_mode()
    fn = getattr(reader, "entity_attributes", None)
    if mode == "off" or fn is None or not entities:
        return {}
    try:
        raw = fn([e.id for e in entities])
    except Exception as exc:  # noqa: BLE001 — answer without details instead
        subject = type(reader).__name__
        if _first_time("ASK_ATTRIBUTES_UNAVAILABLE", subject):
            raven_log(
                "WARN", "record attributes query failed; answering without them",
                criticality="P3", service=_SERVICE,
                error_code="ASK_ATTRIBUTES_UNAVAILABLE",
                context=_fallback_context(subject, workspace_id,
                                          "ASK_ATTRIBUTES_UNAVAILABLE", str(exc)))
        return {}
    return {eid: _scrub(attrs, mode) for eid, attrs in raw.items()}


def format_attributes(attrs: dict[str, Any], display_name: str = "") -> str:
    """Render ``key=value`` pairs for one record, or '' when there are none.

    Skips empty values, nested objects/lists, and any value that just repeats
    the record's display name; caps the count and the length of each value.
    """
    parts: list[str] = []
    for key, value in attrs.items():
        if value is None or value == "" or isinstance(value, (dict, list)):
            continue
        text = str(value).strip()
        if not text or text == display_name:
            continue
        if len(text) > MAX_VALUE_CHARS:
            text = text[:MAX_VALUE_CHARS - 1] + "…"
        parts.append(f"{key}={text}")
        if len(parts) >= MAX_ATTRIBUTES:
            break
    return ", ".join(parts)


def summarise_neighbors(neighbors: list[dict[str, Any]]) -> str:
    """Count linked records by relationship, direction and type.

    ``10 x Contract (<- CONTRACT_CUSTOMERS)`` style, so a small model reads a
    ready-made total instead of counting a long list line by line.
    """
    counts: Counter[tuple[str, str, str]] = Counter(
        (str(n.get("relationship", "")), str(n.get("direction", "")),
         str(n.get("type", ""))) for n in neighbors)
    parts = []
    for (rel, direction, kind), n in sorted(counts.items(),
                                            key=lambda kv: (-kv[1], kv[0])):
        arrow = "->" if direction == "out" else "<-"
        parts.append(f"{n} x {kind} ({arrow} {rel})")
    return ", ".join(parts)


def _key_rank(key: str, values: dict[str, int]) -> tuple[int, int, str]:
    """Sort key: preferred names first, then the key most records carry, then A-Z."""
    low = key.lower()
    preferred = _PREFERRED_KEYS.index(low) if low in _PREFERRED_KEYS else len(_PREFERRED_KEYS)
    return (preferred, -sum(values.values()), key)


def format_breakdown(by_attribute: dict[str, dict[str, int]]) -> list[str]:
    """Render one type's categorical attributes as ``key: value n, value n`` lines.

    When there are more keys than ``MAX_BREAKDOWN_KEYS``, ``status``-like keys
    win, then the keys carried by the most records (never just the first
    letters of the alphabet).
    """
    ranked = sorted(by_attribute, key=lambda k: _key_rank(k, by_attribute[k]))
    lines = []
    for key in ranked[:MAX_BREAKDOWN_KEYS]:
        values = sorted(by_attribute[key].items(), key=lambda kv: (-kv[1], kv[0]))
        lines.append(f"{key}: " + ", ".join(f"{v} {n}" for v, n in values))
    return lines
