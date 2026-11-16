"""Connect-flow behaviour of datasource_api and datasource_ingest_api.

Covers: verify-before-save (a failed test must not leave a saved row that
blocks the retry), clear duplicate-name errors, plain-English connection
errors that never leak the password, and the saved-datasource ingest route
(workspace-scoped, mapping deferred to the background job).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aryx.api.datasource_api import datasource_router
from aryx.api.datasource_ingest_api import datasource_ingest_router
from aryx.connectors.connection_errors import friendly_db_error, redact

MOD = "aryx.api.datasource_api"
ING = "aryx.api.datasource_ingest_api"
PW = "s3cr@t:pw/#1"
CFG = {"host": "db.example.com", "port": "5432", "database": "example_db",
       "user": "example_user", "extra_context": "Support cases and supply chain"}


@pytest.fixture
def store():
    s = MagicMock()
    s.list.return_value = []
    s.add.return_value = {"id": 10, "workspace_id": 1, "name": "pg", "kind": "postgres"}
    s.get.return_value = {"id": 10, "workspace_id": 1, "name": "pg",
                          "kind": "postgres", "config": CFG}
    s.secret_of.return_value = PW
    return s


@pytest.fixture
def client(store):
    settings = MagicMock(rdb_dsn="postgresql://t")
    with patch(f"{MOD}.get_settings", return_value=settings), \
         patch(f"{MOD}.DatasourceStore", return_value=store), \
         patch(f"{ING}.get_settings", return_value=settings), \
         patch(f"{ING}.DatasourceStore", return_value=store):
        app = FastAPI()
        app.include_router(datasource_router())
        app.include_router(datasource_ingest_router())
        yield TestClient(app, raise_server_exceptions=False)


def _add(client, **over):
    body = {"name": "pg", "kind": "postgres", "config": CFG,
            "secret": PW, "workspace_id": 1, "verify": True, **over}
    return client.post("/admin/datasources", json=body)


def test_verify_failure_does_not_save(client, store) -> None:
    with patch(f"{MOD}._ping", return_value={"ok": False, "error": "Can't reach"}):
        r = _add(client)
    assert r.status_code == 400
    assert "Can't reach" in r.json()["detail"]
    store.add.assert_not_called()


def test_verify_success_saves_and_returns_tables(client, store) -> None:
    with patch(f"{MOD}._ping", return_value={"ok": True, "tables": ["a", "b"],
                                             "table_count": 2}):
        r = _add(client)
    assert r.status_code == 200
    assert r.json()["tables"] == ["a", "b"]
    store.add.assert_called_once()


def test_without_verify_saves_without_testing(client, store) -> None:
    with patch(f"{MOD}._ping") as ping:
        r = _add(client, verify=False)
    assert r.status_code == 200
    ping.assert_not_called()


def test_duplicate_name_is_409_with_clear_message(client, store) -> None:
    store.list.return_value = [{"name": "pg"}]
    r = _add(client)
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]
    store.add.assert_not_called()


def test_missing_context_rejected(client, store) -> None:
    r = _add(client, config={**CFG, "extra_context": "  "})
    assert r.status_code == 400
    assert "extra_context is required" in r.json()["detail"]


def test_ping_lists_up_to_200_tables() -> None:
    from aryx.api import datasource_api
    with patch(f"{MOD}.test_connection"), \
         patch(f"{MOD}.introspect", return_value=[]) as intro:
        datasource_api._ping("postgres", CFG, PW)
    assert intro.call_args.kwargs["max_tables"] == 200


SCHEMA = [{"table": "supply_chain", "columns": ["po_number", "line_number"],
           "pk": ["po_number", "line_number"], "fks": []},
          {"table": "cases", "columns": ["case_id"], "pk": ["case_id"], "fks": []}]


def test_ingest_queues_job_and_defers_mapping(client, store) -> None:
    with patch(f"{ING}.introspect", return_value=SCHEMA), \
         patch(f"{ING}.apply_migrations"), \
         patch(f"{ING}.JobStore") as jobs, \
         patch(f"{ING}.run_cancellable") as run:
        r = client.post("/admin/datasources/10/ingest", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued" and body["job_id"]
    assert body["tables"] == ["supply_chain", "cases"]
    jobs.return_value.create.assert_called_once()
    # run_cancellable(map_and_ingest, dsn, job_id, ws, url, schema, context, job_id, ws)
    args = run.call_args.args
    assert args[0].__name__ == "map_and_ingest"
    assert args[3] == 1                      # cancel scope in the datasource's workspace
    assert args[5] == SCHEMA                 # full schema incl. composite PK
    assert args[6] == CFG["extra_context"]
    assert args[8] == 1


def test_ingest_selected_tables_only(client, store) -> None:
    with patch(f"{ING}.introspect", return_value=SCHEMA), \
         patch(f"{ING}.apply_migrations"), patch(f"{ING}.JobStore"), \
         patch(f"{ING}.run_cancellable") as run:
        r = client.post("/admin/datasources/10/ingest", json={"tables": ["cases"]})
    assert r.status_code == 200
    assert [t["table"] for t in run.call_args.args[5]] == ["cases"]


def test_ingest_other_workspace_is_404(client, store) -> None:
    with patch(f"{ING}.introspect") as intro, \
         patch(f"{ING}.run_cancellable") as run:
        r = client.post("/admin/datasources/10/ingest", json={"workspace_id": 5})
    assert r.status_code == 404
    intro.assert_not_called()
    run.assert_not_called()
    store.secret_of.assert_not_called()


def test_ingest_same_workspace_allowed(client, store) -> None:
    with patch(f"{ING}.introspect", return_value=SCHEMA), \
         patch(f"{ING}.apply_migrations"), patch(f"{ING}.JobStore"), \
         patch(f"{ING}.run_cancellable"):
        r = client.post("/admin/datasources/10/ingest", json={"workspace_id": 1})
    assert r.status_code == 200


def test_ingest_unknown_table_rejected(client, store) -> None:
    with patch(f"{ING}.introspect", return_value=[
            {"table": "cases", "columns": [], "pk": [], "fks": []}]):
        r = client.post("/admin/datasources/10/ingest", json={"tables": ["nope"]})
    assert r.status_code == 400
    assert "unknown table" in r.json()["detail"]


def test_ingest_connection_error_is_friendly_and_redacted(client, store) -> None:
    err = Exception(f'connection to server at "db.example.com", port 5432 '
                    f'failed: timeout expired ({PW})')
    with patch(f"{ING}.introspect", side_effect=err):
        r = client.post("/admin/datasources/10/ingest", json={})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "Can't reach the database at db.example.com:5432" in detail
    assert PW not in detail


def test_ingest_404(client, store) -> None:
    store.get.return_value = None
    assert client.post("/admin/datasources/99/ingest", json={}).status_code == 404


@pytest.mark.parametrize("raw, expect", [
    ('FATAL:  password authentication failed for user "example_user"',
     "Username or password is wrong"),
    ('FATAL:  database "example_db" does not exist', "Database 'example_db' doesn't exist"),
    ('FATAL:  permission denied for database "example_db"',
     "doesn't have permission to connect to database 'example_db'"),
    ("failed to resolve host 'pw@db.example.com': [Errno -2] Name or service not known",
     "Host 'db.example.com' could not be found"),
    ("server closed the connection unexpectedly", "Can't reach the database"),
    ("connection refused", "Can't reach the database"),
    ("SSL error: certificate verify failed", "SSL/TLS handshake"),
    ('invalid sslmode value: "sometimes"', "Connection failed: invalid sslmode"),
    ("something odd (Background on this error at: https://sqlalche.me/e/20/e3q8)",
     "Connection failed: something odd"),
])
def test_friendly_messages(raw: str, expect: str) -> None:
    msg = friendly_db_error(raw, host="db.example.com", port="5432",
                            database="example_db")
    assert expect in msg
    assert "sqlalche.me" not in msg


def test_redact_hides_raw_encoded_and_url_password() -> None:
    enc = "s3cr%40t%3Apw%2F%231"
    text = f"pw {PW} enc {enc} url postgresql+psycopg://u:whatever@h/d"
    out = redact(text, PW)
    assert PW not in out and enc not in out
    assert "whatever" not in out and "u:***@h" in out
