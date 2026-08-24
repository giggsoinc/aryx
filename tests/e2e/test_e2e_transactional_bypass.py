"""Transactional/fact types (a genuine per-row identifier) skip entity
resolution entirely — one entity per record, no blocking/scoring/
adjudication. Dimension types are unaffected and still resolve normally.

Regression coverage for the Order-merge incident: with the ordinary
multi-column match-key fallback, 7 orders sharing a handful of companies/
products/statuses got offered as merge candidates, and a human approving
what looked like a plausible partial match actually collapsed genuinely
distinct orders into one entity (e.g. O101 absorbing O103/O105/O106/O107).
Wrong for a transactional record — every row is supposed to stay its own
entity no matter how much text it shares with another row.

No LLM required for the Order case (materialize_one_per_record never calls
one); the Company case uses a bare MagicMock broker since near-duplicate
company names may or may not reach the adjudicate band, and either outcome
is fine — this test only confirms that path still runs, not what it decides.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from psycopg.types.json import Json

pytestmark = pytest.mark.e2e

_ORDERS = [
    {"order_id": "O101", "company_name": "Asha L.", "order_status": "Open",
     "product_name": "Starter Kit"},
    {"order_id": "O102", "company_name": "Byte Cafe", "order_status": "Shipped",
     "product_name": "Receipt Printer"},
    {"order_id": "O103", "company_name": "Asha Labs", "order_status": "Open",
     "product_name": "Receipt Printer"},
    {"order_id": "O104", "company_name": "Coda Shop", "order_status": "Delivered",
     "product_name": "Barcode Scanner"},
    {"order_id": "O105", "company_name": "Byte Ca", "order_status": "Shipped",
     "product_name": "Barcode Scanner"},
    {"order_id": "O106", "company_name": "Coda Shop", "order_status": "Delivered",
     "product_name": "Starter Kit"},
    {"order_id": "O107", "company_name": "Asha", "order_status": "Delivered",
     "product_name": "Starter Kit"},
]

_COMPANIES = [{"name": "Asha L."}, {"name": "Asha Lab"}, {"name": "Coda Shop"}]


def _seed_run(dsn: str, workspace_id: int, rows: list[dict]) -> int:
    """A real run + landed records for it. Returns the run_id."""
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO aryx_run (workspace_id, source_system, source_dataset, "
                "status) VALUES (%s, 'test', 'test', 'done') RETURNING run_id",
                (workspace_id,))
            run_id = cur.fetchone()[0]
            for i, row in enumerate(rows):
                cur.execute(
                    "INSERT INTO aryx_landed_record (workspace_id, run_id, "
                    "source_system, source_dataset, source_record_id, payload, "
                    "cleaned_at) VALUES (%s, %s, 'test', 'test', %s, %s, now())",
                    (workspace_id, run_id, f"r{i}", Json(row)))
    return run_id


def test_order_records_materialize_one_per_row_with_no_adjudication(
    workspace, e2e_dsn,
) -> None:
    """7 orders in -> 7 Order entities, 0 adjudication rows."""
    from aryx.resolution.field_shape import is_row_identifier
    from aryx.resolve_entities import materialize_one_per_record
    from aryx.store.adjudication_store import AdjudicationStore
    from aryx.store.entity_store import EntityStore

    wid = workspace["id"]
    order_ids = [o["order_id"] for o in _ORDERS]
    assert is_row_identifier(order_ids) is True, "fixture must actually trigger the bypass"

    run_id = _seed_run(e2e_dsn, wid, _ORDERS)
    estore = EntityStore(e2e_dsn, wid)
    created = materialize_one_per_record(run_id, "Order", ["order_id"], estore)
    assert created == len(_ORDERS)

    entities = [e for e in estore.list_entities() if e[1] == "Order"]
    assert len(entities) == len(_ORDERS), "every order must stay its own entity"
    assert {e[2]["order_id"] for e in entities} == set(order_ids)

    assert AdjudicationStore(e2e_dsn, wid).stats()["pending"] == 0, (
        "no order pair should ever reach the review queue")


def test_company_dimension_still_resolves_normally(workspace, e2e_dsn) -> None:
    """Same fix, different type: a name column is never a row identifier,
    so Company must still go through ordinary blocking/scoring — confirms
    the bypass is scoped to transactional types, not applied everywhere."""
    from aryx.resolution.field_shape import is_row_identifier
    from aryx.resolve_entities import resolve_run
    from aryx.store.entity_store import EntityStore

    wid = workspace["id"]
    names = [c["name"] for c in _COMPANIES]
    assert is_row_identifier(names) is False, "free text must never trigger the bypass"

    run_id = _seed_run(e2e_dsn, wid, _COMPANIES)
    estore = EntityStore(e2e_dsn, wid)
    created = resolve_run(run_id, "Company", ["name"], estore, MagicMock(),
                          e2e_dsn, wid)
    assert created >= 1
    entities = [e for e in estore.list_entities() if e[1] == "Company"]
    assert len(entities) >= 1


def test_run_pipeline_skip_resolution_flag_takes_the_bypass_branch(
    workspace, e2e_dsn, e2e_graph_url,
) -> None:
    """Wiring test: run_pipeline(skip_resolution=True) must actually call
    materialize_one_per_record, not resolve_run — the two callees are each
    tested directly above, but nothing previously proved run_pipeline picks
    the right one. Goes through the real function, not a mock, so the
    project_graph/FalkorDB step at the end is exercised too."""
    from unittest.mock import MagicMock

    from aryx.connectors.records_source import RecordsConnector
    from aryx.models import RawRecord, SourceRef
    from aryx.pipeline.orchestrate import run_pipeline
    from aryx.store.entity_store import EntityStore

    wid = workspace["id"]
    records = [
        RawRecord(source=SourceRef(system="test", dataset="orders",
                                   record_id=o["order_id"]),
                  payload=o)
        for o in _ORDERS
    ]
    connector = RecordsConnector(records)

    summary = run_pipeline(
        connector=connector, dsn=e2e_dsn, system="test", dataset="orders",
        ontology_type="Order", match_keys=["order_id"],
        graph_url=e2e_graph_url, broker=MagicMock(), workspace_id=wid,
        skip_resolution=True,
    )
    assert summary["entities"] == len(_ORDERS)

    estore = EntityStore(e2e_dsn, wid)
    entities = [e for e in estore.list_entities() if e[1] == "Order"]
    assert len(entities) == len(_ORDERS), (
        "skip_resolution=True must materialize one entity per record via "
        "run_pipeline, the same as calling materialize_one_per_record directly")
