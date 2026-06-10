"""Night 3 — OWL import round-trip + domain validator + SHACL emission."""
from __future__ import annotations

from rdflib import Namespace
from rdflib.namespace import RDF

from aryx.ontology.rdf.importer_full import parse_ontology_full
from aryx.ontology.rdf.shapes import SH, build_shapes_graph
from aryx.reasoning.axiom_validator import _is_subtype, _violates_domain


_TTL = """
@prefix aryx: <https://aryx.local/ontology#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

aryx:Vehicle a owl:Class .
aryx:Car     a owl:Class ; rdfs:subClassOf aryx:Vehicle .
aryx:Sedan   a owl:Class ; rdfs:subClassOf aryx:Car .
aryx:Person  a owl:Class ; owl:disjointWith aryx:Company .
aryx:Company a owl:Class ; owl:equivalentClass aryx:Org .
aryx:Org     a owl:Class .

aryx:age     a owl:DatatypeProperty ; rdfs:domain aryx:Person ;
             rdfs:range xsd:integer .
aryx:owns    a owl:ObjectProperty ; rdfs:domain aryx:Person ;
             rdfs:range aryx:Vehicle .

aryx:Person rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty aryx:ssn ;
    owl:maxCardinality "1"^^xsd:nonNegativeInteger
] .
"""


# ---------- importer round-trip ----------

def test_import_extracts_hierarchy() -> None:
    out = parse_ontology_full(_TTL, "turtle")
    assert out["hierarchy"]["Car"] == "Vehicle"
    assert out["hierarchy"]["Sedan"] == "Car"


def test_import_extracts_disjoint_and_equivalent() -> None:
    out = parse_ontology_full(_TTL, "turtle")
    kinds = {(a["subject_type"], a["kind"]): a["payload"]
             for a in out["axioms"]}
    assert kinds[("Person", "disjoint_with")] == {"object_type": "Company"}
    assert kinds[("Company", "equivalent_to")] == {"object_type": "Org"}


def test_import_extracts_domain_and_range_class() -> None:
    out = parse_ontology_full(_TTL, "turtle")
    pairs = {(a["subject_type"], a["kind"], a["payload"].get("property"))
             for a in out["axioms"]}
    assert ("Person", "domain", "age") in pairs
    assert ("Person", "domain", "owns") in pairs
    # range(owns) -> Vehicle stored with subject_type=Vehicle
    range_axioms = [a for a in out["axioms"] if a["kind"] == "range"]
    assert any(a["payload"].get("class") == "Vehicle" for a in range_axioms)


def test_import_extracts_cardinality_restriction() -> None:
    out = parse_ontology_full(_TTL, "turtle")
    card = [a for a in out["axioms"] if a["kind"] == "cardinality_max"]
    assert any(a["subject_type"] == "Person"
               and a["payload"] == {"property": "ssn", "max": 1}
               for a in card)


def test_import_types_are_proposed() -> None:
    out = parse_ontology_full(_TTL, "turtle")
    assert {t.status for t in out["types"]} == {"proposed"}
    assert {t.source for t in out["types"]} == {"owl-import"}


# ---------- domain validator (ancestor-aware) ----------

_ANC = {"Vehicle": [], "Car": ["Vehicle"], "Sedan": ["Car", "Vehicle"],
        "Person": [], "Company": []}


def test_is_subtype_handles_self_and_ancestor() -> None:
    assert _is_subtype("Sedan", "Vehicle", _ANC)
    assert _is_subtype("Vehicle", "Vehicle", _ANC)
    assert not _is_subtype("Person", "Vehicle", _ANC)


def test_domain_violation_when_wrong_type_carries_property() -> None:
    # Axiom: owns has domain Vehicle. Person carries 'owns' -> violation.
    assert _violates_domain({"owns": "v1"}, {"property": "owns"},
                            "Person", "Vehicle", _ANC)


def test_domain_satisfied_when_subtype_carries_property() -> None:
    # Sedan is a Vehicle -> no violation.
    assert not _violates_domain({"owns": "v1"}, {"property": "owns"},
                                "Sedan", "Vehicle", _ANC)


def test_domain_no_violation_when_property_absent() -> None:
    assert not _violates_domain({}, {"property": "owns"},
                                "Person", "Vehicle", _ANC)


# ---------- SHACL shapes emission ----------

def test_shapes_emit_nodeshape_per_subject_type() -> None:
    axioms = [{"id": 1, "subject_type": "Person", "kind": "cardinality_max",
               "payload": {"property": "ssn", "max": 1}}]
    g = build_shapes_graph(axioms, base_uri="https://aryx.local/")
    nodeshapes = list(g.subjects(RDF.type, SH.NodeShape))
    assert len(nodeshapes) == 1


def test_shapes_emit_max_count_constraint() -> None:
    axioms = [{"id": 1, "subject_type": "Person", "kind": "cardinality_max",
               "payload": {"property": "ssn", "max": 1}}]
    g = build_shapes_graph(axioms, base_uri="https://aryx.local/")
    assert list(g.triples((None, SH.maxCount, None)))


def test_shapes_emit_sh_class_for_range_class() -> None:
    axioms = [{"id": 1, "subject_type": "Vehicle", "kind": "range",
               "payload": {"property": "owns", "class": "Vehicle"}}]
    g = build_shapes_graph(axioms, base_uri="https://aryx.local/")
    assert list(g.triples((None, SH["class"], None)))


def test_shapes_skip_orphan_range_subject() -> None:
    # subject_type=_property (datatype range) is skipped.
    axioms = [{"id": 1, "subject_type": "_property", "kind": "range",
               "payload": {"property": "age", "datatype": "integer"}}]
    g = build_shapes_graph(axioms, base_uri="https://aryx.local/")
    assert list(g.subjects(RDF.type, SH.NodeShape)) == []
