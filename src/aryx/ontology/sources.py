"""Ontology seed sources — pluggable grounding for the mapping agent.

Priority when available: your DD/MDM (authoritative) > domain ontology >
schema.org (general) > pure induction. MDM and RDF/OWL adapters are future work.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Protocol

from aryx.models import OntologyType

# Minimal schema.org-style vocabulary so the agent names types consistently.
_SCHEMA_ORG_LITE: list[tuple[str, list[str]]] = [
    ("Organization", ["name", "email", "phone", "address", "country"]),
    ("Person", ["name", "email", "phone", "address"]),
    ("Product", ["name", "sku", "price", "description"]),
    ("Order", ["order_id", "date", "amount", "status"]),
    ("Place", ["name", "address", "country", "latitude", "longitude"]),
]


class OntologySource(Protocol):
    """Yields canonical types used to ground the mapping agent."""

    def load(self) -> list[OntologyType]:
        """Return seed ontology types."""
        ...


class SchemaOrgSource:
    """A small schema.org-style vocabulary for consistent type naming."""

    def load(self) -> list[OntologyType]:
        """Return the built-in schema.org-lite seed (pre-approved)."""
        return [
            OntologyType(name=name, attributes=attrs, status="approved",
                         source="schema.org")
            for name, attrs in _SCHEMA_ORG_LITE
        ]


class DataDictionarySource:
    """Loads an existing Data Dictionary CSV — the authoritative seed.

    Expected columns: 'type', 'attribute'. Rows group by type.
    """

    def __init__(self, path: Path) -> None:
        """Configure the source from a DD CSV path."""
        self._path = path

    def load(self) -> list[OntologyType]:
        """Read the DD CSV into approved ontology types."""
        grouped: dict[str, list[str]] = {}
        with self._path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                grouped.setdefault(row["type"], []).append(row["attribute"])
        return [
            OntologyType(name=name, attributes=attrs, status="approved", source="dd")
            for name, attrs in grouped.items()
        ]
