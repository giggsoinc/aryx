"""Adapter: map a saved Brief (workspace_api.BriefRequest) onto a C01
UserIntentRequest so saving the Brief can feed intent capture directly,
instead of requiring a second, disconnected manual capture step.

Brief and Intent are different shapes with only partial overlap — this is a
best-effort, lossy mapping, not a schema unification:
  - `domain` carries over directly (same field, same meaning in both).
  - `objective` <- Brief's `aim` (closest analogue: "what should the
    knowledge model make possible").
  - `target_audience` <- the first of Brief's `roles`, if any (Intent's
    field is scalar; Brief's is a list — only the first role survives).
  - `uploaded_file` <- the first `source_docs` filename, or else a synthetic
    `brief:workspace_{id}` marker, since Intent requires it but a Brief can
    be saved before any dataset is uploaded.
  - `scope`, `objectives`, `questions` have no home in UserIntentRequest and
    are intentionally dropped.
"""
from __future__ import annotations

from aryx.intent.models import UserIntentRequest


def brief_to_intent_request(brief: dict, workspace_id: int) -> UserIntentRequest:
    """Build a `UserIntentRequest` from a saved Brief dict."""
    source_docs = brief.get("source_docs") or []
    roles = brief.get("roles") or []
    uploaded_file = source_docs[0] if source_docs else f"brief:workspace_{workspace_id}"
    target_audience = roles[0] if roles else ""
    return UserIntentRequest(
        uploaded_file=uploaded_file,
        domain=brief.get("domain") or "",
        objective=brief.get("aim") or "",
        target_audience=target_audience,
    )
