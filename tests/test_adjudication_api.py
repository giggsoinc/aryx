"""Route-contract tests for adjudication_api.py's preview endpoint.

Raven-review finding: preview() had zero test coverage. These prove two
things the router-under-mock can verify cheaply: a missing adjudication id
404s, and — the actual regression target — preview only ever calls the
SCOPED EntityStore methods (entities_by_ids/relationships_for_entities/
members_provenance_for_entities), never the workspace-wide list_entities/
list_relationships/list_members_provenance it used to load in full for a
single pending-row preview.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tests.test_api_routes import _client


def _row(left=100, right=200) -> dict:
    return {"id": 1, "score": 0.86, "llm_verdict": 0.6, "llm_reason": "band",
            "status": "pending", "left_record_id": left, "right_record_id": right}


def test_preview_404_when_adjudication_missing() -> None:
    from aryx.api.adjudication_api import adjudication_router

    store_cls = MagicMock()
    store_cls.return_value.get.return_value = None
    resp = _client(adjudication_router, "aryx.api.adjudication_api",
                   AdjudicationStore=store_cls).get("/adjudication/999/preview")

    assert resp.status_code == 404


def test_preview_uses_scoped_entity_queries_not_workspace_wide() -> None:
    from aryx.api.adjudication_api import adjudication_router

    store_cls = MagicMock()
    store = store_cls.return_value
    store.get.return_value = _row()
    store.entity_of_record.side_effect = lambda rid: {100: 10, 200: 20}[rid]
    store.raw_records.return_value = {}

    estore_cls = MagicMock()
    estore = estore_cls.return_value
    estore.relationships_for_entities.return_value = []
    estore.entities_by_ids.return_value = [
        (10, "Company", {"name": "Left Co"}),
        (20, "Company", {"name": "Right Co"}),
    ]
    estore.members_provenance_for_entities.return_value = []

    resp = _client(adjudication_router, "aryx.api.adjudication_api",
                   AdjudicationStore=store_cls, EntityStore=estore_cls,
                   ).get("/adjudication/1/preview")

    assert resp.status_code == 200
    body = resp.json()
    assert body["left"]["entity_id"] == 10
    assert body["right"]["entity_id"] == 20
    assert body["left"]["name"] == "Left Co"
    assert body["right"]["name"] == "Right Co"

    # The regression this test exists for: no workspace-wide scan.
    estore.list_entities.assert_not_called()
    estore.list_relationships.assert_not_called()
    estore.list_members_provenance.assert_not_called()

    # Scoped to exactly the two entities being previewed (no neighbours here).
    estore.entities_by_ids.assert_called_once()
    assert set(estore.entities_by_ids.call_args[0][0]) == {10, 20}
    estore.relationships_for_entities.assert_called_once_with([10, 20])
    estore.members_provenance_for_entities.assert_called_once_with([10, 20])


def test_preview_falls_back_to_raw_record_when_side_has_no_entity() -> None:
    """A record not yet resolved into an entity still previews via its raw
    landed payload instead of erroring."""
    from aryx.api.adjudication_api import adjudication_router

    store_cls = MagicMock()
    store = store_cls.return_value
    store.get.return_value = _row(left=100, right=200)
    store.entity_of_record.side_effect = lambda rid: None if rid == 200 else 10
    store.raw_records.return_value = {200: {"name": "Unresolved"}}

    estore_cls = MagicMock()
    estore = estore_cls.return_value
    estore.relationships_for_entities.return_value = []
    estore.entities_by_ids.return_value = [(10, "Company", {"name": "Left Co"})]
    estore.members_provenance_for_entities.return_value = []

    resp = _client(adjudication_router, "aryx.api.adjudication_api",
                   AdjudicationStore=store_cls, EntityStore=estore_cls,
                   ).get("/adjudication/1/preview")

    assert resp.status_code == 200
    body = resp.json()
    assert body["left"]["entity_id"] == 10
    assert body["right"]["entity_id"] is None
    assert body["right"]["attributes"] == {"name": "Unresolved"}
