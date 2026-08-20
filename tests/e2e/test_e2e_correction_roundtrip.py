"""Chain 6: correction_apply mutates the graph and the mutation is real and
visible afterward. correction_propose is exercised too, but only for "does
it respond cleanly" — its own endpoint (/corrections/chat) calls a real LLM
inside the already-running api container, which this test process cannot
stub (it's a separate process). That endpoint currently has a pre-existing,
unrelated bug (a Gemini thinking-effort config issue, found during manual
smoke testing) — this test documents that rather than hiding it, and keeps
its real assertion on correction_apply, which never touches an LLM at all.

Marked e2e_llm (excluded from CI, local-only) because seeding an entity to
correct goes through the same real, unstubbable entity-extraction LLM call
as chain 5 — see that file's docstring for why.
"""
from __future__ import annotations

import base64
import time

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_llm]

_CSV = b"id,name,region\n1,Acme,west\n2,Globex,east\n"


def _seed_entity(workspace_id: int) -> dict:
    """Ingest a tiny CSV and return the first extracted entity."""
    from aryx.mcp.ingest_hitl import dispatch as ingest_dispatch
    started = ingest_dispatch("ingest_file", {
        "workspace_id": workspace_id,
        "files": [{"filename": "e2e.csv", "content_base64": base64.b64encode(_CSV).decode()}],
    })
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status = ingest_dispatch("ingest_status",
                                 {"workspace_id": workspace_id, "job_id": started["job_id"]})
        if (status.get("job") or {}).get("status") == "complete":
            break
        time.sleep(1)
    preview = ingest_dispatch("entities_preview", {"workspace_id": workspace_id, "limit": 5})
    entities = preview.get("entities") or []
    assert entities, "seed ingest produced no entities to correct"
    return entities[0]


def test_correction_apply_mutates_the_graph(workspace) -> None:
    """Retype a real, freshly-extracted entity; confirm the type actually
    changed in the graph afterward — not just that the call returned 200."""
    from aryx.mcp.correction import dispatch
    wid = workspace["id"]
    entity = _seed_entity(wid)

    result = dispatch("correction_apply", {
        "workspace_id": wid, "kind": "retype",
        "entity_id": entity["id"], "name": "TestEntityType",
    })
    assert result["kind"] == "retype"
    assert result["object"] == "TestEntityType"

    from aryx.mcp.ingest_hitl import dispatch as ingest_dispatch
    preview = ingest_dispatch("entities_preview", {"workspace_id": wid, "limit": 20})
    retyped = next(e for e in preview["entities"] if e["id"] == entity["id"])
    assert retyped["type"] == "TestEntityType"


def test_correction_propose_responds_cleanly(workspace) -> None:
    """Not a happy-path assertion — see module docstring. Goes through the
    real server.call_tool() entry point, not dispatch() directly — that's
    where HTTP errors get caught into a clean {"error": ...} shape (proved
    live during manual smoke testing); dispatch() alone lets them raise."""
    import asyncio
    import json

    from aryx.mcp.server import call_tool
    result = asyncio.run(call_tool(
        "correction_propose", {"workspace_id": workspace["id"], "text": "X is a Y"}))
    parsed = json.loads(result[0].text)
    assert isinstance(parsed, dict)
