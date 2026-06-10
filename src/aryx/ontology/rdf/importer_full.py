"""Full OWL round-trip parser — types + hierarchy + axioms in one pass.

Built on top of ``importer.parse_ontology`` (which only returns classes), this
module re-parses the same document to also extract:

  - ``rdfs:subClassOf``           -> hierarchy[child] = parent
  - ``owl:disjointWith`` / ``owl:equivalentClass`` -> pair axioms
  - ``rdfs:domain`` / ``rdfs:range``                -> property axioms
  - ``owl:Restriction`` (onProperty + maxCardinality) -> cardinality_max

Output shape lets ``ontology_browse.import_doc`` persist everything via
``OntologyStore.set_parent`` + ``AxiomStore.add``. Idempotent because all
downstream stores are.
"""
from __future__ import annotations

import logging

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from aryx.ontology.rdf.importer import _label, _local_name, parse_ontology
from aryx.ontology.rdf.model import FORMATS

logger = logging.getLogger(__name__)


def parse_ontology_full(content: str, fmt: str) -> dict:
    """Parse a document into types + hierarchy + axioms for full round-trip."""
    types = parse_ontology(content, fmt)
    graph = Graph()
    graph.parse(data=content, format=FORMATS[fmt][0])
    name_by_iri = _class_name_index(graph)
    hierarchy = _extract_hierarchy(graph, name_by_iri)
    axioms: list[dict] = []
    axioms += _extract_pair_axioms(graph, name_by_iri,
                                   OWL.disjointWith, "disjoint_with")
    axioms += _extract_pair_axioms(graph, name_by_iri,
                                   OWL.equivalentClass, "equivalent_to")
    axioms += _extract_property_axioms(graph, name_by_iri)
    axioms += _extract_restrictions(graph, name_by_iri)
    logger.info("ontology import full classes=%d hierarchy=%d axioms=%d",
                len(types), len(hierarchy), len(axioms))
    return {"types": types, "hierarchy": hierarchy, "axioms": axioms}


def _class_name_index(graph: Graph) -> dict:
    """Map class IRIs to their canonical names (label or local fragment)."""
    out: dict = {}
    for cls in graph.subjects(RDF.type, OWL.Class):
        if isinstance(cls, URIRef):
            out[cls] = _label(graph, cls)
    for cls in graph.subjects(RDF.type, RDFS.Class):
        if isinstance(cls, URIRef):
            out.setdefault(cls, _label(graph, cls))
    return out


def _extract_hierarchy(graph: Graph, name_by_iri: dict) -> dict:
    """Read direct rdfs:subClassOf edges (skip BNode restriction targets)."""
    hierarchy: dict = {}
    for child, parent in graph.subject_objects(RDFS.subClassOf):
        if not (isinstance(child, URIRef) and isinstance(parent, URIRef)):
            continue
        cname = name_by_iri.get(child) or _label(graph, child)
        pname = name_by_iri.get(parent) or _label(graph, parent)
        if cname and pname and cname != pname:
            hierarchy[cname] = pname
    return hierarchy


def _extract_pair_axioms(graph: Graph, name_by_iri: dict,
                         predicate, kind: str) -> list[dict]:
    """Extract A predicate B class-pair axioms (disjoint_with / equivalent_to)."""
    out: list[dict] = []
    for subj, obj in graph.subject_objects(predicate):
        if not (isinstance(subj, URIRef) and isinstance(obj, URIRef)):
            continue
        s = name_by_iri.get(subj) or _label(graph, subj)
        o = name_by_iri.get(obj) or _label(graph, obj)
        if s and o:
            out.append({"subject_type": s, "kind": kind,
                        "payload": {"object_type": o}})
    return out


def _extract_property_axioms(graph: Graph, name_by_iri: dict) -> list[dict]:
    """Extract rdfs:domain / rdfs:range as domain + range axioms."""
    out: list[dict] = []
    for prop, domain in graph.subject_objects(RDFS.domain):
        if not (isinstance(prop, URIRef) and isinstance(domain, URIRef)):
            continue
        dname = name_by_iri.get(domain) or _label(graph, domain)
        if dname:
            out.append({"subject_type": dname, "kind": "domain",
                        "payload": {"property": _label(graph, prop)}})
    for prop, rng in graph.subject_objects(RDFS.range):
        if not isinstance(prop, URIRef):
            continue
        payload = {"property": _label(graph, prop)}
        if isinstance(rng, URIRef) and rng in name_by_iri:
            payload["class"] = name_by_iri[rng]
            subject = name_by_iri[rng]
        elif isinstance(rng, URIRef) and str(rng).startswith(str(XSD)):
            payload["datatype"] = _local_name(rng)
            subject = "_property"
        else:
            continue
        out.append({"subject_type": subject, "kind": "range",
                    "payload": payload})
    return out


def _extract_restrictions(graph: Graph, name_by_iri: dict) -> list[dict]:
    """Walk owl:Restriction blocks behind rdfs:subClassOf to cardinality_max."""
    out: list[dict] = []
    for cls, restriction in graph.subject_objects(RDFS.subClassOf):
        if not (isinstance(cls, URIRef) and isinstance(restriction, BNode)):
            continue
        if (restriction, RDF.type, OWL.Restriction) not in graph:
            continue
        prop = next(graph.objects(restriction, OWL.onProperty), None)
        max_card = next(graph.objects(restriction, OWL.maxCardinality), None)
        if not (isinstance(prop, URIRef) and isinstance(max_card, Literal)):
            continue
        try:
            max_int = int(str(max_card))
        except ValueError:
            continue
        cname = name_by_iri.get(cls) or _label(graph, cls)
        out.append({"subject_type": cname, "kind": "cardinality_max",
                    "payload": {"property": _label(graph, prop),
                                "max": max_int}})
    return out
