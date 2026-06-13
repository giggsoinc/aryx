"""MCP ontology dispatch (Slice 4) — get + export to relational/graph/RDF.

ontology_get returns the workspace's approved ontology. ontology_export
emits DDL or RDF: SQL targets (postgres/mysql/snowflake) produce CREATE
TABLE, neo4j produces CREATE CONSTRAINT, rdf/turtle/jsonld returns the
serialised text (via existing /ontology/export). Oracle is a stub.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from aryx.ontology_export_ddl import emit

_API_URL = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")


def _get_types(workspace_id: int) -> dict[str, Any]:
    with urllib.request.urlopen(
        f"{_API_URL}/ontology/types?workspace_id={workspace_id}",
        timeout=30) as r:  # noqa: S310
        return json.loads(r.read().decode()) or {}


def _get_rdf(workspace_id: int, fmt: str) -> str:
    with urllib.request.urlopen(
        f"{_API_URL}/ontology/export?workspace_id={workspace_id}"
        f"&format={fmt}", timeout=60) as r:  # noqa: S310
        return r.read().decode(errors="replace")


def dispatch(name: str, a: dict) -> Any:
    """Route an ontology_* MCP call."""
    if name == "ontology_get":
        return _get_types(int(a["workspace_id"]))
    if name == "ontology_export":
        wid = int(a["workspace_id"])
        target = (a.get("target") or "").lower()
        if target in ("rdf", "turtle", "json-ld", "jsonld", "xml", "owl"):
            fmt = "json-ld" if target in ("jsonld", "json-ld") else target
            fmt = "turtle" if fmt in ("rdf", "owl") else fmt
            return {"target": "rdf", "format": fmt,
                    "payload": _get_rdf(wid, fmt)}
        types_doc = _get_types(wid)
        return emit(target, types_doc)
    return {"error": f"unknown ontology tool: {name}"}
