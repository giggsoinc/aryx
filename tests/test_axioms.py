"""Night 2 axiom-layer tests — AxiomStore hashing, OWL emission, validator."""
from __future__ import annotations

from rdflib.namespace import OWL

from aryx.models import OntologyType
from aryx.ontology.rdf import GraphBundle
from aryx.ontology.rdf.exporter import build_graph


# ---------- Night 2: AxiomStore canonical hash ----------

def test_axiom_canonical_hash_is_key_order_invariant() -> None:
    from aryx.store.axiom_store import _canonical_hash
    a = _canonical_hash({"property": "age", "max": 1})
    b = _canonical_hash({"max": 1, "property": "age"})
    assert a == b


def test_axiom_canonical_hash_differs_on_value_change() -> None:
    from aryx.store.axiom_store import _canonical_hash
    a = _canonical_hash({"property": "age", "max": 1})
    b = _canonical_hash({"property": "age", "max": 2})
    assert a != b


# ---------- Night 2: exporter emits OWL axiom triples ----------

def _bundle_with_axioms(axioms: list[dict]) -> GraphBundle:
    return GraphBundle(
        types=[OntologyType(name="Person"), OntologyType(name="Company")],
        entities=[], relationships=[], provenance=[], axioms=axioms,
    )


def test_exporter_emits_disjoint_with() -> None:
    g = build_graph(
        _bundle_with_axioms([{
            "id": 1, "subject_type": "Person", "kind": "disjoint_with",
            "payload": {"object_type": "Company"},
        }]),
        base_uri="https://aryx.local/", include_provenance=False,
    )
    assert list(g.triples((None, OWL.disjointWith, None)))


def test_exporter_emits_equivalent_class() -> None:
    g = build_graph(
        _bundle_with_axioms([{
            "id": 2, "subject_type": "Person", "kind": "equivalent_to",
            "payload": {"object_type": "Company"},
        }]),
        base_uri="https://aryx.local/", include_provenance=False,
    )
    assert list(g.triples((None, OWL.equivalentClass, None)))


def test_exporter_emits_cardinality_restriction() -> None:
    g = build_graph(
        _bundle_with_axioms([{
            "id": 3, "subject_type": "Person", "kind": "cardinality_max",
            "payload": {"property": "ssn", "max": 1},
        }]),
        base_uri="https://aryx.local/", include_provenance=False,
    )
    assert list(g.triples((None, OWL.maxCardinality, None)))
    assert list(g.triples((None, OWL.onProperty, None)))


# ---------- Night 2: cardinality validator ----------

def test_cardinality_max_violation_detected() -> None:
    from aryx.reasoning.axiom_validator import _violates_cardinality_max
    violated, count = _violates_cardinality_max(
        {"ssn": ["a", "b"]}, {"property": "ssn", "max": 1},
    )
    assert violated and count == 2


def test_cardinality_max_within_bound_passes() -> None:
    from aryx.reasoning.axiom_validator import _violates_cardinality_max
    violated, count = _violates_cardinality_max(
        {"ssn": "only-one"}, {"property": "ssn", "max": 1},
    )
    assert not violated and count == 1


def test_cardinality_max_missing_property_is_zero() -> None:
    from aryx.reasoning.axiom_validator import _violates_cardinality_max
    violated, count = _violates_cardinality_max(
        {}, {"property": "ssn", "max": 1},
    )
    assert not violated and count == 0
