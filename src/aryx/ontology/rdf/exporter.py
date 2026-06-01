"""Serialise a workspace knowledge graph to RDF/OWL for third-party tools.

Maps Aryx's property-graph shape onto OWL/RDF so the result loads cleanly in
Protege, GraphDB, Apache Jena, and any SPARQL store:

  - each ontology type   -> owl:Class
  - each attribute        -> owl:DatatypeProperty (rdfs:domain = its class)
  - each relationship     -> owl:ObjectProperty
  - each resolved entity  -> owl:NamedIndividual (rdf:type its class)
  - provenance (optional) -> aryx:source literals on each individual

Output is on-demand and read-only; it never mutates the source of truth.
"""
from __future__ import annotations

import logging

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from aryx.ontology.rdf.model import (
    FORMATS,
    GraphBundle,
    entity_label,
    slug,
)

logger = logging.getLogger(__name__)


def _namespaces(base_uri: str) -> tuple[Namespace, Namespace]:
    """Build the ontology (classes/props) and entity (individuals) namespaces."""
    base = base_uri if base_uri.endswith("/") else base_uri + "/"
    return Namespace(f"{base}ontology#"), Namespace(f"{base}entity/")


def build_graph(bundle: GraphBundle, base_uri: str,
                include_provenance: bool = True) -> Graph:
    """Construct an in-memory rdflib Graph from a GraphBundle.

    Args:
        bundle: The workspace graph in store-native tuples.
        base_uri: URI prefix for minted class/property/individual IRIs.
        include_provenance: When True, attach source literals per entity.

    Returns:
        A populated, namespace-bound rdflib Graph ready to serialise.
    """
    onto, ent = _namespaces(base_uri)
    graph = Graph()
    graph.bind("aryx", onto)
    graph.bind("ent", ent)
    graph.bind("owl", OWL)
    graph.bind("rdfs", RDFS)

    onto_node = URIRef(str(onto).rstrip("#"))
    graph.add((onto_node, RDF.type, OWL.Ontology))

    declared_classes: set[str] = set()
    declared_props: set[str] = set()

    def ensure_class(type_name: str) -> URIRef:
        """Declare an owl:Class for a type once; return its IRI."""
        node = onto[slug(type_name)]
        if type_name not in declared_classes:
            graph.add((node, RDF.type, OWL.Class))
            graph.add((node, RDFS.label, Literal(type_name)))
            declared_classes.add(type_name)
        return node

    def ensure_datatype_prop(attr: str, domain: URIRef) -> URIRef:
        """Declare an owl:DatatypeProperty once with its domain; return its IRI."""
        node = onto[slug(attr)]
        if attr not in declared_props:
            graph.add((node, RDF.type, OWL.DatatypeProperty))
            graph.add((node, RDFS.label, Literal(attr)))
            graph.add((node, RDFS.domain, domain))
            declared_props.add(attr)
        return node

    # 1) Declared ontology types -> owl:Class + their attribute properties.
    for otype in bundle.types:
        cls = ensure_class(otype.name)
        for attr in otype.attributes:
            ensure_datatype_prop(attr, cls)

    # 2) Resolved entities -> individuals with typed attribute literals.
    for entity_id, type_name, attributes in bundle.entities:
        cls = ensure_class(type_name)
        individual = ent[str(entity_id)]
        graph.add((individual, RDF.type, OWL.NamedIndividual))
        graph.add((individual, RDF.type, cls))
        label = entity_label(attributes)
        if label:
            graph.add((individual, RDFS.label, Literal(label)))
        for key, value in (attributes or {}).items():
            if value is None or value == "":
                continue
            prop = ensure_datatype_prop(str(key), cls)
            graph.add((individual, prop, Literal(str(value), datatype=XSD.string)))
        if include_provenance:
            for ent_id, system, dataset, record_id in bundle.provenance:
                if ent_id == entity_id:
                    src = f"{system}:{dataset}:{record_id}"
                    graph.add((individual, onto["source"], Literal(src)))

    # 3) Relationships -> owl:ObjectProperty assertions between individuals.
    declared_edges: set[str] = set()
    for source_id, target_id, name in bundle.relationships:
        predicate = onto[slug(name)]
        if name not in declared_edges:
            graph.add((predicate, RDF.type, OWL.ObjectProperty))
            graph.add((predicate, RDFS.label, Literal(name)))
            declared_edges.add(name)
        graph.add((ent[str(source_id)], predicate, ent[str(target_id)]))

    return graph


def serialize(bundle: GraphBundle, fmt: str, base_uri: str,
              include_provenance: bool = True) -> tuple[bytes, str, str]:
    """Serialise a GraphBundle to the requested RDF format.

    Args:
        bundle: The workspace graph to export.
        fmt: A FORMATS key ('turtle', 'json-ld', 'xml', 'n-triples').
        base_uri: URI prefix for minted IRIs.
        include_provenance: Whether to attach source provenance literals.

    Returns:
        (payload_bytes, media_type, file_extension).

    Raises:
        ValueError: If fmt is not a supported format.
    """
    if fmt not in FORMATS:
        raise ValueError(f"unsupported format '{fmt}'; choose from {sorted(FORMATS)}")
    rdflib_fmt, media_type, extension = FORMATS[fmt]
    graph = build_graph(bundle, base_uri, include_provenance)
    payload = graph.serialize(format=rdflib_fmt, encoding="utf-8")
    if isinstance(payload, str):  # some rdflib serialisers return str
        payload = payload.encode("utf-8")
    logger.info("ontology exported format=%s triples=%d bytes=%d",
                fmt, len(graph), len(payload))
    return payload, media_type, extension
