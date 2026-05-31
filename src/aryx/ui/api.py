"""Thin HTTP client over the Aryx REST API for the Streamlit UI."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

_BASE = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")

_WS = {"id": 1}


def set_workspace(workspace_id: int) -> None:
    """Set the active workspace for all subsequent scoped calls."""
    _WS["id"] = int(workspace_id)


def current_workspace() -> int:
    return _WS["id"]


def _get(path: str) -> Any:
    sep = "&" if "?" in path else "?"
    url = f"{_BASE}{path}{sep}workspace_id={_WS['id']}"
    with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310
        return json.loads(r.read())


def _post(path: str, body: dict, timeout: int = 30) -> Any:
    data = json.dumps({"workspace_id": _WS["id"], **body}).encode()
    req = urllib.request.Request(
        f"{_BASE}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read())


def _delete(path: str) -> Any:
    req = urllib.request.Request(f"{_BASE}{path}", method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        return json.loads(r.read())


def list_workspaces() -> list[dict]:
    return _get("/admin/workspaces")


def create_workspace(name: str, description: str = "") -> dict:
    return _post("/admin/workspaces", {"name": name, "description": description})


def delete_workspace(workspace_id: int) -> dict:
    return _delete(f"/admin/workspaces/{workspace_id}")


def full_graph() -> dict[str, Any]:
    return _get("/graph")


def search_entities(name: str = "", etype: str = "") -> list[dict]:
    params = []
    if name:
        params.append(f"name={urllib.parse.quote(name)}")
    if etype:
        params.append(f"type={urllib.parse.quote(etype)}")
    qs = "?" + "&".join(params) if params else ""
    return _get(f"/entities{qs}")


def get_neighbors(entity_id: int) -> list[dict]:
    return _get(f"/entities/{entity_id}/neighbors")


def get_provenance(entity_id: int) -> list[dict]:
    return _get(f"/entities/{entity_id}/provenance")


def get_path(src: int, dst: int) -> list[dict]:
    return _get(f"/entities/{src}/path/{dst}")


def list_runs() -> list[dict]:
    return _get("/admin/runs")


def list_jobs() -> list[dict]:
    return _get("/admin/jobs")


def get_job(job_id: str) -> dict[str, Any]:
    return _get(f"/admin/jobs/{job_id}")


def ingest_db(table: str, ontology_type: str, match_keys: str,
              system: str = "postgresql", key_column: str = "id",
              fk_links: list[dict] | None = None) -> dict:
    return _post("/admin/ingest/db", {
        "table": table, "ontology_type": ontology_type,
        "match_keys": match_keys, "system": system, "key_column": key_column,
        "fk_links": fk_links or [],
    })


def ask(question: str, history: list[dict] | None = None) -> dict[str, Any]:
    return _post("/ask", {"question": question, "history": history or []}, timeout=180)


def get_llm_config() -> dict[str, Any]:
    return _get("/llm/config")


def set_llm_config(cfg: dict) -> dict[str, Any]:
    return _post("/admin/llm/config", cfg)


def observability() -> dict[str, Any]:
    return _get("/admin/observability")


def db_connect(cfg: dict) -> dict[str, Any]:
    return _post("/admin/connect", cfg, timeout=60)


def db_discover(connection_id: str, context: str) -> dict[str, Any]:
    return _post("/admin/discover", {"connection_id": connection_id, "context": context}, timeout=180)


def ingest_multi(connection_id: str, tables: list[dict], edges: list[dict]) -> dict[str, Any]:
    return _post("/admin/ingest/multi",
                 {"connection_id": connection_id, "tables": tables, "edges": edges})


def docs_summary(discovery_id: str) -> dict[str, Any]:
    return _get(f"/admin/docs/summary/{discovery_id}")


def docs_confirm(discovery_id: str, approved_types: list[str], approved_files: list[str]) -> dict[str, Any]:
    return _post("/admin/docs/confirm", {"discovery_id": discovery_id,
                 "approved_types": approved_types, "approved_files": approved_files})
