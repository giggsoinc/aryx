"""Night 1 Protege-parity tests — exercises the in-memory layers only.

The Postgres layer is faked so this test file runs without a live stack. The
SQL behind the edge axioms is covered against a real database in
tests/e2e/test_inferred_edges.py.
"""
from __future__ import annotations

from rdflib.namespace import OWL, RDFS

from aryx.models import OntologyType
from aryx.ontology.rdf import GraphBundle
from aryx.ontology.rdf.exporter import build_graph
from aryx.reasoning import edge_axioms as reng
from aryx.store.inferred_store import TRANSITIVE_MAX


# ---------- Phase 4: exporter emits rdfs:subClassOf ----------

def test_exporter_emits_subclass_of() -> None:
    bundle = GraphBundle(
        types=[
            OntologyType(name="Vehicle"),
            OntologyType(name="Car", parent_type="Vehicle"),
            OntologyType(name="Sedan", parent_type="Car"),
        ],
        entities=[],
        relationships=[],
        provenance=[],
    )
    g = build_graph(bundle, base_uri="https://aryx.local/", include_provenance=False)
    subclass_triples = list(g.triples((None, RDFS.subClassOf, None)))
    assert len(subclass_triples) == 2  # Car->Vehicle, Sedan->Car
    pairs = {(str(s).rsplit("#", 1)[-1], str(o).rsplit("#", 1)[-1])
             for s, _, o in subclass_triples}
    assert ("Car", "Vehicle") in pairs
    assert ("Sedan", "Car") in pairs


def test_exporter_no_subclass_when_no_parent() -> None:
    bundle = GraphBundle(types=[OntologyType(name="Standalone")])
    g = build_graph(bundle, base_uri="https://aryx.local/", include_provenance=False)
    assert list(g.triples((None, RDFS.subClassOf, None))) == []


# ---------- Phase 3: reasoner edge axioms ----------

class _FakeStore:
    """Records which closure the dispatcher asked the store for."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def apply_inverse(self, edge: str, inverse: str, rule_name: str = "") -> int:
        self.calls.append(("inverse", edge, inverse, rule_name))
        return 0

    def apply_symmetric(self, edge: str, rule_name: str = "") -> int:
        self.calls.append(("symmetric", edge, rule_name))
        return 0

    def apply_transitive(self, edge: str, depth: int, rule_name: str = "") -> int:
        self.calls.append(("transitive", edge, depth, rule_name))
        return 0


def test_apply_inverse_delegates_to_the_store() -> None:
    s = _FakeStore()
    reng.apply_inverse(s, "works_for", "employs", "r1")
    assert s.calls == [("inverse", "works_for", "employs", "r1")]


def test_apply_symmetric_delegates_to_the_store() -> None:
    s = _FakeStore()
    reng.apply_symmetric(s, "sibling_of", "r2")
    assert s.calls == [("symmetric", "sibling_of", "r2")]


def test_apply_transitive_passes_the_requested_depth() -> None:
    s = _FakeStore()
    reng.apply_transitive(s, "located_in", depth=10)  # the store caps it
    assert s.calls == [("transitive", "located_in", 10, "")]


def test_apply_edge_axiom_dispatch_combines() -> None:
    s = _FakeStore()
    fired = reng.apply_edge_axiom(
        s, "located_in",
        {"inverse_of": "contains", "transitive": True, "max_depth": 3}, "r3",
    )
    assert fired == 1
    assert s.calls == [("inverse", "located_in", "contains", "r3"),
                       ("transitive", "located_in", 3, "r3")]


def test_apply_edge_axiom_defaults_transitive_depth_to_the_cap() -> None:
    s = _FakeStore()
    reng.apply_edge_axiom(s, "part_of", {"transitive": True})
    assert s.calls == [("transitive", "part_of", TRANSITIVE_MAX, "")]


def test_apply_edge_axiom_with_no_edge_or_no_axiom_does_nothing() -> None:
    s = _FakeStore()
    assert reng.apply_edge_axiom(s, "", {"symmetric": True}) == 0
    assert reng.apply_edge_axiom(s, "friend", {}) == 0
    assert s.calls == []
