"""Regression: DEC-011's transactional bypass must apply on every ingest
path, not file-upload only.

Found via raven-review: `resolve_match_keys` (the transactional/fact-type
classifier) was only called from file_ingest_api.py. DB-connect, admin
single-table, and CLI ingest all called run_pipeline directly with no
classification at all, so Orders ingested through those paths still went
through full entity resolution and could still be fuzzy-merged — the exact
bug DEC-011 exists to prevent, just reachable through a different door.
Each test feeds a real per-row-identifier column sample through the real
`resolve_match_keys` (not mocked) to prove the wiring is genuine, not a
passthrough.
"""
from __future__ import annotations

import argparse

_ORDER_IDS = [f"ORD{i:03d}" for i in range(50)]  # 100% unique, code-shaped


def test_admin_db_ingest_applies_transactional_bypass(monkeypatch) -> None:
    from aryx.api import admin_api

    captured: dict = {}
    monkeypatch.setattr(admin_api, "JobStore", lambda dsn: _FakeJobStore())
    monkeypatch.setattr(admin_api, "PostgresConnector", lambda **kw: object())
    monkeypatch.setattr(admin_api, "sample_colvals",
                        lambda dsn, table: {"order_id": list(_ORDER_IDS)})
    monkeypatch.setattr(admin_api, "_local_broker", lambda: object())
    monkeypatch.setattr(admin_api, "run_pipeline",
                        lambda **kw: captured.update(kw) or {"run_id": 1})

    req = admin_api.IngestDbRequest(table="orders", ontology_type="Order",
                                    match_keys="order_id")
    admin_api._run_db(req, "job-1")

    assert captured["skip_resolution"] is True
    assert captured["match_keys"] == ["order_id"]


def test_cli_run_applies_transactional_bypass(monkeypatch) -> None:
    from aryx import cli

    captured: dict = {}
    monkeypatch.setattr(cli, "apply_migrations", lambda dsn: None)
    monkeypatch.setattr(cli, "PostgresConnector", lambda **kw: object())
    monkeypatch.setattr(cli, "sample_colvals",
                        lambda dsn, table: {"order_id": list(_ORDER_IDS)})
    monkeypatch.setattr(cli, "default_broker", lambda: object())
    monkeypatch.setattr(cli, "run_pipeline",
                        lambda **kw: captured.update(kw) or {"run_id": 1})

    args = argparse.Namespace(table="orders", type="Order",
                              match_keys="order_id", key_column="id",
                              system="postgresql", tag=False, relate=False)
    cli._run(args)

    assert captured["skip_resolution"] is True
    assert captured["match_keys"] == ["order_id"]


def test_connect_multi_ingest_applies_transactional_bypass(monkeypatch) -> None:
    from aryx.api import connect_api

    captured: list[dict] = []
    monkeypatch.setattr(connect_api, "JobStore", lambda dsn: _FakeJobStore())
    monkeypatch.setattr(connect_api, "_local_broker", lambda: object())
    monkeypatch.setattr(connect_api, "sample_colvals",
                        lambda url, table: {"order_id": list(_ORDER_IDS)})
    monkeypatch.setattr(connect_api, "SqlConnector", lambda *a, **kw: object())
    monkeypatch.setattr(connect_api, "run_pipeline",
                        lambda **kw: captured.append(kw) or {"run_id": 1})

    connect_api._run_multi(
        "postgresql://fake", [{"table": "orders", "ontology_type": "Order",
                               "match_keys": ["order_id"]}], [], "job-1")

    assert len(captured) == 1
    assert captured[0]["skip_resolution"] is True
    assert captured[0]["match_keys"] == ["order_id"]


class _FakeJobStore:
    def update_stage(self, *a, **k) -> None:
        pass

    def finish(self, *a, **k) -> None:
        pass

    def close(self) -> None:
        pass
