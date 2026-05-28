"""Ontology mapping (stage 6): pluggable seed sources + the mapping agent."""

from aryx.ontology.mapping import categorize
from aryx.ontology.sources import (
    DataDictionarySource,
    OntologySource,
    SchemaOrgSource,
)

__all__ = ["categorize", "OntologySource", "SchemaOrgSource", "DataDictionarySource"]
