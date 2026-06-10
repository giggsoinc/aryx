"""Derive a SHACL shapes graph from workspace axioms.

Emits a ``sh:NodeShape`` per subject_type that has any constraint axiom,
attaching ``sh:property`` shapes for cardinality / domain / range. Lets an
external SHACL validator (Protégé + TopBraid plugin, pyshacl, Apache Jena)
check workspace entity data against the constraints declared in Aryx.

Disjoint / equivalent are class-level OWL axioms; SHACL models them via
``sh:not`` patterns that need entity-level evaluation, so they are left to
the OWL exporter rather than duplicated here.
"""
from __future__ import annotations

import logging

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from aryx.ontology.rdf.model import slug

logger = logging.getLogger(__name__)

SH = Namespace("http://www.w3.org/ns/shacl#")


def build_shapes_graph(axioms: list[dict], base_uri: str) -> Graph:
    """Build an in-memory SHACL shapes graph from workspace axioms."""
    base = base_uri if base_uri.endswith("/") else base_uri + "/"
    onto = Namespace(f"{base}ontology#")
    shape_ns = Namespace(f"{base}shape/")
    graph = Graph()
    graph.bind("sh", SH)
    graph.bind("aryx", onto)
    graph.bind("shape", shape_ns)
    graph.bind("xsd", XSD)

    shapes_by_type: dict[str, URIRef] = {}

    def shape_for(type_name: str) -> URIRef:
        """Get-or-create the NodeShape node for ``type_name``."""
        if type_name not in shapes_by_type:
            node = shape_ns[slug(type_name)]
            graph.add((node, RDF.type, SH.NodeShape))
            graph.add((node, SH.targetClass, onto[slug(type_name)]))
            shapes_by_type[type_name] = node
        return shapes_by_type[type_name]

    for ax in axioms or []:
        kind = ax["kind"]
        payload = ax.get("payload") or {}
        if kind == "cardinality_max" and payload.get("property"):
            _emit_max_count(graph, onto, shape_for(ax["subject_type"]),
                            payload)
        elif kind == "domain" and payload.get("property"):
            _emit_presence(graph, onto, shape_for(ax["subject_type"]),
                           payload)
        elif kind == "range" and payload.get("property"):
            subject = ax["subject_type"]
            if subject and subject != "_property":
                _emit_range(graph, onto, shape_for(subject), payload)

    logger.info("SHACL shapes built nodeshapes=%d triples=%d",
                len(shapes_by_type), len(graph))
    return graph


def _emit_max_count(graph: Graph, onto: Namespace, node: URIRef,
                    payload: dict) -> None:
    """Attach ``sh:property [ sh:path P ; sh:maxCount N ]`` to the shape."""
    prop_shape = BNode()
    graph.add((node, SH.property, prop_shape))
    graph.add((prop_shape, SH.path, onto[slug(str(payload["property"]))]))
    graph.add((prop_shape, SH.maxCount,
               Literal(int(payload.get("max", 1)),
                       datatype=XSD.nonNegativeInteger)))


def _emit_presence(graph: Graph, onto: Namespace, node: URIRef,
                   payload: dict) -> None:
    """Attach ``sh:property [ sh:path P ]`` — domain marker (no constraint)."""
    prop_shape = BNode()
    graph.add((node, SH.property, prop_shape))
    graph.add((prop_shape, SH.path, onto[slug(str(payload["property"]))]))


def _emit_range(graph: Graph, onto: Namespace, node: URIRef,
                payload: dict) -> None:
    """Attach ``sh:property`` with ``sh:class`` or ``sh:datatype``."""
    prop_shape = BNode()
    graph.add((node, SH.property, prop_shape))
    graph.add((prop_shape, SH.path, onto[slug(str(payload["property"]))]))
    if payload.get("class"):
        graph.add((prop_shape, SH["class"],
                   onto[slug(str(payload["class"]))]))
    elif payload.get("datatype"):
        local = str(payload["datatype"]).split(":")[-1]
        graph.add((prop_shape, SH.datatype,
                   getattr(XSD, local, XSD.string)))
