"""Policy-driven golden-record assembly over cluster members (G3).

Builds per-attribute contributions from member records and applies the
workspace survivorship policy. Returns the merged record, a provenance map,
and the conflict rows destined for ``aryx_attribute_conflict``.
"""
from __future__ import annotations

from typing import Any

from aryx.resolution.survivorship import (
    _EMPTY,
    Contribution,
    SurvivorshipPolicy,
    resolve_attribute,
)


def golden_record_with_policy(
    members: list[dict[str, Any]],
    policy: SurvivorshipPolicy,
) -> tuple[dict[str, Any], dict[str, int], list[dict[str, Any]]]:
    """Merge cluster members under a survivorship policy.

    Args:
        members: One dict per member with keys ``payload`` (dict),
            ``record_id`` (int), ``source_system`` (str | None) and
            ``cleaned_at`` (comparable timestamp | None).
        policy: The survivorship policy to apply.

    Returns:
        (merged_attributes, provenance {attr: record_id}, conflict_rows).
    """
    completeness = {
        m["record_id"]: sum(1 for v in m["payload"].values() if v not in _EMPTY)
        for m in members
    }

    by_attr: dict[str, list[Contribution]] = {}
    for m in members:
        for key, value in m["payload"].items():
            if value in _EMPTY:
                continue
            by_attr.setdefault(key, []).append(Contribution(
                value=value,
                source_system=m.get("source_system"),
                cleaned_at=m.get("cleaned_at"),
                record_id=m["record_id"],
                completeness=completeness[m["record_id"]],
            ))

    merged: dict[str, Any] = {}
    provenance: dict[str, int] = {}
    conflicts: list[dict[str, Any]] = []
    for attr, contribs in by_attr.items():
        winner, conflict = resolve_attribute(attr, contribs, policy)
        merged[attr] = winner.value
        provenance[attr] = winner.record_id
        if conflict is not None:
            conflicts.append(conflict)
    return merged, provenance, conflicts
