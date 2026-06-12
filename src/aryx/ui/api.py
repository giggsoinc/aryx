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
    """Return the id of the currently selected workspace."""
    return _WS["id"]


def _get(path: str) -> Any:
    """GET a path, appending the active workspace id, and decode JSON."""
    sep = "&" if "?" in path else "?"
    url = f"{_BASE}{path}{sep}workspace_id={_WS['id']}"
    with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310
        return json.loads(r.read())


def _post(path: str, body: dict, timeout: int = 30) -> Any:
    """POST a JSON body (merged with the workspace id) and decode the reply."""
    data = json.dumps({"workspace_id": _WS["id"], **body}).encode()
    req = urllib.request.Request(
        f"{_BASE}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read())


def _post_raw(path: str, body: bytes = b"{}", timeout: int = 30) -> Any:
    req = urllib.request.Request(
        f"{_BASE}{path}", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read())


def _delete(path: str) -> Any:
    req = urllib.request.Request(f"{_BASE}{path}", method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        return json.loads(r.read())


def list_workspaces() -> list[dict]:
    return _get("/admin/workspaces")


def create_workspace(name: str, description: str = "", context: str = "") -> dict:
    return _post("/admin/workspaces",
                 {"name": name, "description": description, "context": context})


def delete_workspace(workspace_id: int) -> dict:
    return _delete(f"/admin/workspaces/{workspace_id}")


def purge_workspace(workspace_id: int) -> dict:
    return _post_raw(f"/admin/workspaces/{workspace_id}/purge", timeout=60)


def nuke_system() -> dict:
    return _post_raw("/admin/workspaces/nuke", timeout=120)


def set_workspace_context(workspace_id: int, context: str) -> dict:
    data = json.dumps({"context": context}).encode()
    req = urllib.request.Request(
        f"{_BASE}/admin/workspaces/{workspace_id}/context",
        data=data, headers={"Content-Type": "application/json"}, method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        return json.loads(r.read())


def set_workspace_brief(workspace_id: int, brief: dict) -> dict:
    data = json.dumps(brief).encode()
    req = urllib.request.Request(
        f"{_BASE}/admin/workspaces/{workspace_id}/brief",
        data=data, headers={"Content-Type": "application/json"}, method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
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


def ask(question: str, history: list[dict] | None = None) -> dict[str, Any]:
    return _post("/ask", {"question": question, "history": history or []}, timeout=180)


def get_llm_config() -> dict[str, Any]:
    return _get("/llm/config")


def set_llm_config(cfg: dict) -> dict[str, Any]:
    return _post("/admin/llm/config", cfg)


def observability() -> dict[str, Any]:
    return _get("/admin/observability")
