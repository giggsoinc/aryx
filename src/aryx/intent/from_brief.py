"""Adapter: map a saved Brief (workspace_api.BriefRequest) onto a C01
UserIntentRequest so saving the Brief feeds intent capture directly,
instead of requiring a second, disconnected manual capture step.

Brief and Intent are different shapes. The scalar overlap maps directly:
  - `domain` carries over (same field, same meaning in both).
  - `objective` <- Brief's `aim` (closest analogue: "what should the
    knowledge model make possible").
  - `target_audience` <- the first of Brief's `roles`; Intent's field is
    scalar, so the remaining roles ride in `brief_context.roles`.
  - `uploaded_file` <- the first `source_docs` filename, or else a synthetic
    `brief:workspace_{id}` marker, since Intent requires it but the Brief is
    authored BEFORE any dataset is uploaded — that ordering is the point.

Everything with no scalar home — `scope`, `objectives`, `questions`, the
full `roles` list — is carried through `brief_context` (UserIntent schema
1.1) rather than dropped, so planning and dashboard composition see the
whole customer brief. Before 1.1 these were silently discarded and the
dashboard could only ever reflect domain + aim.
"""
from __future__ import annotations

from aryx.intent.models import BriefContext, UserIntentRequest


def _slist(value: object) -> list[str]:
    """Coerce a brief list field to a clean list of non-empty strings."""
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def brief_to_intent_request(brief: dict, workspace_id: int) -> UserIntentRequest:
    """Build a `UserIntentRequest` from a saved Brief dict."""
    source_docs = _slist(brief.get("source_docs"))
    roles = _slist(brief.get("roles"))
    objectives = _slist(brief.get("objectives"))
    questions = _slist(brief.get("questions"))
    uploaded_file = source_docs[0] if source_docs else f"brief:workspace_{workspace_id}"
    return UserIntentRequest(
        uploaded_file=uploaded_file,
        domain=str(brief.get("domain") or "").strip(),
        objective=str(brief.get("aim") or "").strip(),
        target_audience=roles[0] if roles else "",
        brief_context=BriefContext(
            scope=str(brief.get("scope") or "").strip(),
            objectives=objectives,
            questions=questions,
            roles=roles,
        ),
    )
