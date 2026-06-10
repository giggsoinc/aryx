"""OWL/RDFS triple emission for ontology axioms (Night 2).

Kept separate from ``exporter`` so each module stays within the 150-line cap.
Each axiom kind maps onto well-known triples Protégé and Jena enforce on
import.
"""
from __future__ import annotations

from collections.abc import Callable

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from aryx.ontology.rdf.model import slug


def emit_axioms(graph: Graph, onto: Namespace, axioms: list[dict],
                ensure_class: Callable[[str], URIRef]) -> None:
    """Add OWL/RDFS triples for every axiom in ``axioms`` to ``graph``."""
    for ax in axioms or []:
        subj_cls = ensure_class(ax["subject_type"])
        kind = ax["kind"]
        payload = ax.get("payload") or {}
        if kind == "disjoint_with" and payload.get("object_type"):
            graph.add((subj_cls, OWL.disjointWith,
                       ensure_class(str(payload["object_type"]))))
        elif kind == "equivalent_to" and payload.get("object_type"):
            graph.add((subj_cls, OWL.equivalentClass,
                       ensure_class(str(payload["object_type"]))))
        elif kind == "domain" and payload.get("property"):
            prop = onto[slug(str(payload["property"]))]
            graph.add((prop, RDFS.domain, subj_cls))
        elif kind == "range" and payload.get("property"):
            _emit_range(graph, onto, payload, ensure_class)
        elif kind == "cardinality_max" and payload.get("property"):
            _emit_cardinality_max(graph, onto, subj_cls, payload)


def _emit_range(graph: Graph, onto: Namespace, payload: dict,
                ensure_class: Callable[[str], URIRef]) -> None:
    """Emit rdfs:range — either an object class or an XSD datatype."""
    prop = onto[slug(str(payload["property"]))]
    if payload.get("class"):
        graph.add((prop, RDF.type, OWL.ObjectProperty))
        graph.add((prop, RDFS.range, ensure_class(str(payload["class"]))))
    elif payload.get("datatype"):
        local = str(payload["datatype"]).split(":")[-1]
        graph.add((prop, RDFS.range, getattr(XSD, local, XSD.string)))


def _emit_cardinality_max(graph: Graph, onto: Namespace,
                          subj_cls: URIRef, payload: dict) -> None:
    """Emit an owl:Restriction blank node for owl:maxCardinality."""
    prop = onto[slug(str(payload["property"]))]
    restriction = BNode()
    graph.add((subj_cls, RDFS.subClassOf, restriction))
    graph.add((restriction, RDF.type, OWL.Restriction))
    graph.add((restriction, OWL.onProperty, prop))
    graph.add((restriction, OWL.maxCardinality,
               Literal(int(payload.get("max", 1)),
                       datatype=XSD.nonNegativeInteger)))
