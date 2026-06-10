"""Neutral data model + helpers shared by the RDF/OWL exporter and importer.

Decouples the rdflib serialisation layer from the Postgres stores: callers
build a GraphBundle (plain tuples read from EntityStore/OntologyStore) and the
exporter turns it into triples. Keeps SQL and rdflib concerns separate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from aryx.models import OntologyType

# UI/format name -> (rdflib serialiser name, media type, file extension).
FORMATS: dict[str, tuple[str, str, str]] = {
    "turtle": ("turtle", "text/turtle", "ttl"),
    "json-ld": ("json-ld", "application/ld+json", "jsonld"),
    "xml": ("xml", "application/rdf+xml", "rdf"),
    "n-triples": ("nt", "application/n-triples", "nt"),
}

# Common file extensions -> format key, for import auto-detection.
_EXT_TO_FORMAT: dict[str, str] = {
    "ttl": "turtle", "turtle": "turtle", "n3": "turtle",
    "jsonld": "json-ld", "json": "json-ld",
    "rdf": "xml", "owl": "xml", "xml": "xml",
    "nt": "n-triples",
}

_SLUG_RE = re.compile(r"[^A-Za-z0-9_]+")

# Attribute keys (case-insensitive) preferred when deriving an entity label.
_LABEL_KEYS = ("name", "full_name", "title", "label", "display_name", "email")


@dataclass
class GraphBundle:
    """A workspace's graph in store-native tuples, ready to serialise.

    Attributes:
        entities: (entity_id, ontology_type, attributes) golden records.
        relationships: (source_entity_id, target_entity_id, name) edges.
        types: Declared ontology types (classes + their attribute names).
        provenance: Optional (entity_id, system, dataset, record_id) edges.
    """

    entities: list[tuple[int, str, dict]] = field(default_factory=list)
    relationships: list[tuple[int, int, str]] = field(default_factory=list)
    types: list[OntologyType] = field(default_factory=list)
    provenance: list[tuple[int, str, str, str]] = field(default_factory=list)
    axioms: list[dict] = field(default_factory=list)


def slug(text: str) -> str:
    """Make a safe URI local-name from a type/attribute/relationship label.

    Collapses non-alphanumeric runs to underscores so the result is a valid,
    readable RDF term (e.g. 'Deal Size ($)' -> 'Deal_Size_').

    Args:
        text: Arbitrary human label.

    Returns:
        A non-empty slug; falls back to 'x' when input has no usable chars.
    """
    cleaned = _SLUG_RE.sub("_", (text or "").strip()).strip("_")
    return cleaned or "x"


def entity_label(attributes: dict) -> str:
    """Pick a human-friendly label for an entity from its golden record.

    Prefers well-known keys (name, title, email, ...); otherwise the first
    non-empty string value; otherwise an empty string.

    Args:
        attributes: The entity's merged attribute dict.

    Returns:
        A display label, or '' when none can be derived.
    """
    lowered = {str(k).lower(): v for k, v in attributes.items()}
    for key in _LABEL_KEYS:
        value = lowered.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in attributes.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def format_for_extension(filename: str) -> str | None:
    """Guess a format key from a filename's extension (for import).

    Args:
        filename: Uploaded file name, e.g. 'crm.ttl'.

    Returns:
        A FORMATS key, or None when the extension is unknown.
    """
    if "." not in (filename or ""):
        return None
    ext = filename.rsplit(".", 1)[-1].lower()
    return _EXT_TO_FORMAT.get(ext)
