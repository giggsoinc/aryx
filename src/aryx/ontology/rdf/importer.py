"""Parse an external OWL/RDF ontology into Aryx ontology types.

Lets a customer bring a standard vocabulary (schema.org, FIBO, a Protege file)
and have its classes seed Aryx's type catalogue. Imported types land as
'proposed' (source='owl-import') so they still pass the human review gate
before the discovery agent relies on them.
"""
from __future__ import annotations

import logging

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from aryx.models import OntologyType
from aryx.ontology.rdf.model import FORMATS

logger = logging.getLogger(__name__)


def _local_name(term: URIRef) -> str:
    """Derive a readable name from an IRI's fragment or last path segment."""
    text = str(term)
    for sep in ("#", "/"):
        if sep in text:
            tail = text.rsplit(sep, 1)[-1]
            if tail:
                return tail
    return text


def _label(graph: Graph, term: URIRef) -> str:
    """Return the rdfs:label of a term, falling back to its local name."""
    for value in graph.objects(term, RDFS.label):
        if str(value).strip():
            return str(value).strip()
    return _local_name(term)


def parse_ontology(content: str, fmt: str) -> list[OntologyType]:
    """Extract ontology types from a serialised RDF/OWL document.

    Classes are read from owl:Class and rdfs:Class declarations. A class's
    attributes are the datatype/object properties whose rdfs:domain is the
    class (deduplicated, sorted).

    Args:
        content: The RDF document text (Turtle, JSON-LD, RDF/XML, N-Triples).
        fmt: A FORMATS key identifying the serialisation.

    Returns:
        One OntologyType per named class, deduplicated by name.

    Raises:
        ValueError: If fmt is unsupported or the document cannot be parsed.
    """
    if fmt not in FORMATS:
        raise ValueError(f"unsupported format '{fmt}'; choose from {sorted(FORMATS)}")
    rdflib_fmt = FORMATS[fmt][0]
    graph = Graph()
    try:
        graph.parse(data=content, format=rdflib_fmt)
    except Exception as exc:  # noqa: BLE001 — surface parse errors to the caller
        raise ValueError(f"could not parse {fmt} document: {exc}") from exc

    classes: set[URIRef] = set()
    for predicate_obj in (OWL.Class, RDFS.Class):
        for subject in graph.subjects(RDF.type, predicate_obj):
            if isinstance(subject, URIRef):
                classes.add(subject)

    # Map each class IRI to the attribute labels of properties it is domain of.
    attrs_by_class: dict[URIRef, set[str]] = {c: set() for c in classes}
    for prop in graph.subjects(RDFS.domain, None):
        if isinstance(prop, BNode):
            continue
        for domain in graph.objects(prop, RDFS.domain):
            if isinstance(domain, URIRef) and domain in attrs_by_class:
                attrs_by_class[domain].add(_label(graph, prop))

    types: dict[str, OntologyType] = {}
    for cls in classes:
        name = _label(graph, cls)
        if name in types:
            continue
        types[name] = OntologyType(
            name=name,
            attributes=sorted(attrs_by_class.get(cls, set())),
            status="proposed",
            source="owl-import",
        )
    result = list(types.values())
    logger.info("ontology import parsed format=%s classes=%d", fmt, len(result))
    return result
