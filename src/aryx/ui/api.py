"""Thin HTTP client over the Aryx REST API for the Streamlit UI."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

_BASE = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")


def _get(path: str) -> Any:
    with urllib.request.urlopen(f"{_BASE}{path}", timeout=10) as r:  # noqa: S310
        return json.loads(r.read())


def _post(path: str, body: dict, timeout: int = 30) -> Any:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{_BASE}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read())


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
              system: str = "postgresql", key_column: str = "id") -> dict:
    return _post("/admin/ingest/db", {
        "table": table, "ontology_type": ontology_type,
        "match_keys": match_keys, "system": system, "key_column": key_column,
    })


def ask(question: str, history: list[dict] | None = None) -> dict[str, Any]:
    return _post("/ask", {"question": question, "history": history or []}, timeout=180)


def get_llm_config() -> dict[str, Any]:
    return _get("/llm/config")


def set_llm_config(cfg: dict) -> dict[str, Any]:
    return _post("/admin/llm/config", cfg)
