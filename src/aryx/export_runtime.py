"""Runtime config for the RDF/OWL interchange plugin (Settings-controlled).

Mirrors aryx.llm_runtime: process-memory state, swappable live from the
Settings panel, never written to disk. Ontology export/import is opt-in
(disabled by default) so it only appears once a customer turns it on.
"""
from __future__ import annotations

import os

from aryx.ontology.rdf.model import FORMATS

_DEFAULT_FORMATS = ["turtle", "json-ld"]


def _initial_formats() -> list[str]:
    raw = os.environ.get("ARYX_ONTOLOGY_FORMATS", "")
    picked = [f.strip() for f in raw.split(",") if f.strip() in FORMATS]
    return picked or list(_DEFAULT_FORMATS)


_state: dict[str, object] = {
    "enabled": os.environ.get("ARYX_ONTOLOGY_ENABLED", "").lower() in {"1", "true", "yes"},
    "formats": _initial_formats(),
    "base_uri": os.environ.get("ARYX_ONTOLOGY_BASE_URI", "https://aryx.local/"),
    "include_provenance": True,
}


def status() -> dict[str, object]:
    """Return the current config plus the full list of available formats."""
    return {
        "enabled": bool(_state["enabled"]),
        "formats": list(_state["formats"]),  # type: ignore[arg-type]
        "base_uri": str(_state["base_uri"]),
        "include_provenance": bool(_state["include_provenance"]),
        "available": list(FORMATS.keys()),
    }


def set_config(enabled: bool | None = None, formats: list[str] | None = None,
               base_uri: str | None = None,
               include_provenance: bool | None = None) -> None:
    """Merge provided fields into the live config (None means 'leave as-is').

    Unknown format names are dropped; an empty selection falls back to the
    defaults so at least one format is always exportable when enabled.
    """
    if enabled is not None:
        _state["enabled"] = bool(enabled)
    if formats is not None:
        valid = [f for f in formats if f in FORMATS]
        _state["formats"] = valid or list(_DEFAULT_FORMATS)
    if base_uri:
        _state["base_uri"] = base_uri.strip()
    if include_provenance is not None:
        _state["include_provenance"] = bool(include_provenance)


def is_enabled() -> bool:
    """Return True when the ontology interchange plugin is turned on."""
    return bool(_state["enabled"])


def enabled_formats() -> list[str]:
    """Return the formats a user may currently export to."""
    return list(_state["formats"])  # type: ignore[arg-type]
