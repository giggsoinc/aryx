"""RDF/OWL interchange plugin — export the graph, import external ontologies.

Public surface for the API layer and UI. The set of supported formats is the
single source of truth in model.FORMATS, so adding a serialisation (e.g. a
future 'trig') is one entry there plus rdflib support — no caller changes.
"""
from __future__ import annotations

from aryx.ontology.rdf.exporter import build_graph, serialize
from aryx.ontology.rdf.importer import parse_ontology
from aryx.ontology.rdf.model import (
    FORMATS,
    GraphBundle,
    format_for_extension,
)

__all__ = [
    "FORMATS",
    "GraphBundle",
    "build_graph",
    "serialize",
    "parse_ontology",
    "format_for_extension",
    "available_formats",
]


def available_formats() -> list[dict[str, str]]:
    """List supported formats with their media type and file extension.

    Returns:
        One dict per format: {name, media_type, extension}.
    """
    return [
        {"name": name, "media_type": media, "extension": ext}
        for name, (_rdflib, media, ext) in FORMATS.items()
    ]
