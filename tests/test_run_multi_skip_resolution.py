"""Which SQL tables may bypass entity resolution (review M1).

Only tables whose rows are known to be distinct real-world things skip:
transactional types, composite-PK line/fact tables, and tables whose match
keys are the PK. A surrogate ``id`` PK next to free-text match keys must
still resolve, or duplicate customers/suppliers would never merge.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from aryx.pipeline import ingest_multi
from aryx.pipeline.ingest_multi import should_skip_resolution


@pytest.mark.parametrize(("pk", "keys", "transactional", "expected"), [
    (["po_number", "line_number"], ["supplier_name"], False, True),  # composite PK
    (["case_id"], ["case_id"], False, True),                          # key IS the PK
    (["id"], ["company_name"], True, True),                           # transactional
    (["case_id"], ["supplier_name"], False, False),                   # surrogate PK
    (["id"], ["company_name", "city"], False, False),                 # surrogate PK
    ([], ["company_name"], False, False),                             # no PK
    (["id"], [], False, False),                                       # nothing to compare
])
def test_should_skip_resolution(pk: list[str], keys: list[str],
                                transactional: bool, expected: bool) -> None:
    assert should_skip_resolution(pk, keys, transactional) is expected


def _run(tables: list[dict]) -> list[dict]:
    """Run run_multi with everything external stubbed; return run_pipeline kwargs."""
    calls: list[dict] = []
    # Repeating, non-ID-shaped sample → resolve_match_keys says "not transactional".
    colvals = {"po_number": ["PO-1", "PO-1", "PO-2"],
               "supplier_name": ["Acme", "Acme", "Globex"]}
    with patch.object(ingest_multi, "get_settings", return_value=MagicMock(rdb_dsn="x")), \
         patch.object(ingest_multi, "JobStore"), \
         patch("aryx.api.admin_api._local_broker"), \
         patch.object(ingest_multi, "SqlConnector"), \
         patch.object(ingest_multi, "sample_colvals", return_value=colvals), \
         patch.object(ingest_multi, "run_pipeline",
                      side_effect=lambda **kw: calls.append(kw)):
        ingest_multi.run_multi("sqlite://", tables, [], "job1", 1)
    return calls


def test_composite_pk_table_skips_resolution() -> None:
    calls = _run([{"table": "supply_chain", "ontology_type": "POLine",
                   "match_keys": ["supplier_name"], "pk": ["po_number", "line_number"]}])
    assert calls[0]["skip_resolution"] is True


def test_surrogate_pk_with_free_text_key_still_resolves() -> None:
    calls = _run([{"table": "suppliers", "ontology_type": "Supplier",
                   "match_keys": ["supplier_name"], "pk": ["case_id"]}])
    assert calls[0]["skip_resolution"] is False


def test_table_without_pk_still_resolves() -> None:
    calls = _run([{"table": "t", "ontology_type": "T", "match_keys": ["supplier_name"]}])
    assert calls[0]["skip_resolution"] is False


def test_map_and_ingest_fails_job_when_nothing_maps() -> None:
    jobs = MagicMock()
    with patch.object(ingest_multi, "get_settings", return_value=MagicMock(rdb_dsn="x")), \
         patch.object(ingest_multi, "JobStore", return_value=jobs), \
         patch.object(ingest_multi, "discover_mappings", return_value={"tables": []}), \
         patch.object(ingest_multi, "run_multi") as run:
        ingest_multi.map_and_ingest("sqlite://", [{"table": "t", "pk": ["id"]}],
                                    "ctx", "job1", 1)
    run.assert_not_called()
    assert jobs.finish.call_args.kwargs["status"] == "failed"


def test_map_and_ingest_carries_pk_into_run_multi() -> None:
    mapping = {"tables": [{"table": "supply_chain", "ontology_type": "POLine",
                           "match_keys": ["supplier_name"]}], "edges": []}
    schema = [{"table": "supply_chain", "pk": ["po_number", "line_number"]}]
    with patch.object(ingest_multi, "get_settings", return_value=MagicMock(rdb_dsn="x")), \
         patch.object(ingest_multi, "JobStore"), \
         patch.object(ingest_multi, "discover_mappings", return_value=mapping), \
         patch.object(ingest_multi, "run_multi") as run:
        ingest_multi.map_and_ingest("sqlite://", schema, "ctx", "job1", 7)
    tables = run.call_args.args[1]
    assert tables[0]["pk"] == ["po_number", "line_number"]
    assert run.call_args.args[4] == 7
