"""HTTP client for the ontology interchange endpoints (UI side).

Split out of aryx.ui.api so that module stays within the line budget. Reuses
api's base URL, workspace selection, and JSON helpers; export needs raw bytes
(a file download) so it issues its own request rather than JSON-decoding.
"""
from __future__ import annotations

import urllib.parse
import urllib.request
from typing import Any

from aryx.ui import api


def config() -> dict[str, Any]:
    """Return the current interchange config and available formats."""
    return api._get("/ontology/config")


def set_config(cfg: dict) -> dict[str, Any]:
    """Persist interchange config (enabled, formats, base URI, provenance)."""
    return api._post("/ontology/config", cfg)


def formats() -> list[dict]:
    """List supported formats with media type and file extension."""
    return api._get("/ontology/formats")


def export(fmt: str) -> bytes:
    """Fetch the active workspace graph serialised to an RDF format (bytes)."""
    base = api._BASE
    ws = api.current_workspace()
    url = f"{base}/ontology/export?workspace_id={ws}&format={urllib.parse.quote(fmt)}"
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310
        return resp.read()


def import_doc(content: str, fmt: str = "", filename: str = "") -> dict[str, Any]:
    """Upload an RDF/OWL document to seed proposed ontology types."""
    return api._post("/ontology/import",
                     {"content": content, "format": fmt, "filename": filename},
                     timeout=120)
