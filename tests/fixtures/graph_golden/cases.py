"""The exact reader calls whose results are frozen as golden output.

``run_cases`` is shared by scripts/capture_graph_golden.py (run once against
live FalkorDB) and the golden e2e test (run against the Postgres reader), so
both sides ask identical questions. Results are normalised: entity ids become
ranks, and lists the old store returned in no defined order are sorted.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from aryx.graph.retrieve import all_types, gather, render_context

from build_fixture import _GHOST, Fixture, to_ranks

_GET_KEYS = ["acme1", "zoe", "falsy0", "emptyname", "emptylist", "booltrue",
             "longonly", "keyorder", "numcode", "floatsku", "widget", "t1",
             "lonely"]
_NEIGHBOR_KEYS = ["acme1", "acme2", "t1", "t2", "loopself", "n1", "n3", "n6",
                  "cyc1", "lonely", "widget", "zoe"]
_PROVENANCE_KEYS = ["acme1", "acme2", "t1", "t2", "t3", "t4", "lonely"]
_NAME_QUERIES = {
    "acme": "acme", "upper": "UPPER", "percent": "%", "underscore": "_",
    "hash": "#", "none": "zzzz", "unicode_upper": "ÜNÏCODE",
    "unicode_lower": "zoë", "empty_string": "", "keyorder": "z-val",
}
# (source_type, relationship, target_type, direction)
_COUNT_CASES = [
    ("Ticket", "raised_by", "Customer", "out"),
    ("Customer", "raised_by", "Ticket", "in"),
    ("Ticket", "raised_by", "Customer", "in"),
    ("Ticket", "mentions", "Customer", "out"),
    ("Ticket", "nope", "Customer", "out"),
    ("Nope", "raised_by", "Customer", "out"),
    ("Node", "next", "Node", "out"),
    ("Customer", "ghost", "Customer", "out"),
]
# (from_key, to_key, max_hops); "ghost" means the nonexistent id
_PATH_CASES = [
    ("n1", "n6", 6), ("n6", "n1", 6), ("n1", "n6", 3), ("n1", "n3", 1),
    ("n1", "n3", 2), ("n1", "n1", 6), ("cyc1", "cyc3", 6), ("cyc3", "cyc1", 6),
    ("lonely", "n1", 6), ("acme1", "ghost", 6), ("t1", "acme1", 6),
    ("acme1", "t1", 6), ("n1", "n6", 99), ("n1", "n6", 0),
    ("sq1", "sq3", 6), ("sq3", "sq1", 6),  # outbound and inbound tie
    ("cyc1", "cyc1", 6), ("loopself", "loopself", 6),  # same node, via cycle / self-loop
]
_GATHER_TERMS = [["Acme"], ["nope"], ["Widget"], ["real_deal"], ["bulk-000"],
                 ["Acme", "Widget"], ["Zoë"]]


def _canon(items: list[Any]) -> list[Any]:
    return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, default=str))


def _find_cases(reader: Any, rank: dict[int, int]) -> dict[str, Any]:
    def r(value: Any) -> Any:
        return _canon(to_ranks(value, rank))

    out = {
        "all_default": r(reader.find_entities()),
        "all_1000": r(reader.find_entities(limit=1000)),
        "limit_0": r(reader.find_entities(limit=0)),
        "limit_negative": r(reader.find_entities(limit=-5)),
        "limit_3": r(reader.find_entities(limit=3)),
        "type_customer": r(reader.find_entities(ontology_type="Customer",
                                                limit=500)),
        "type_unknown": r(reader.find_entities(ontology_type="Nope")),
        "type_and_name": r(reader.find_entities(ontology_type="Customer",
                                                name="acme")),
    }
    for label, term in _NAME_QUERIES.items():
        out[f"name_{label}"] = r(reader.find_entities(name=term, limit=500))
    return out


def _path_cases(reader: Any, fx: Fixture) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for src, dst, hops in _PATH_CASES:
        a = fx.ids[src]
        b = _GHOST if dst == "ghost" else fx.ids[dst]
        out[f"{src}->{dst}@{hops}"] = to_ranks(
            reader.shortest_path(a, b, hops), fx.rank)
    return out


def _ask_cases(reader: Any, fx: Fixture) -> dict[str, Any]:
    # (terms, stable label): the id-lookup term embeds a raw id, so it needs a
    # label that does not change between databases.
    labelled = [(t, "|".join(t)) for t in _GATHER_TERMS]
    labelled.append(([str(fx.ids["t3"])], "id-lookup:t3"))
    out: dict[str, Any] = {"all_types": all_types(reader)}
    for terms, key in labelled:
        entities, calls = gather(reader, terms)
        entities = sorted(entities, key=lambda e: fx.rank.get(e.id, e.id))
        # Sort neighbors/sources AFTER ids become ranks: sorting on raw ids made
        # the order depend on how this database happened to number its entities.
        ranked = to_ranks([asdict(e) for e in entities], fx.rank)
        for d in ranked:
            d["neighbors"] = _canon(d["neighbors"])
            d["sources"] = _canon(d["sources"])
        text = render_context(_rebuild(entities))
        out[key] = {"entities": ranked,
                    "calls": _canon(to_ranks(calls, fx.rank)),
                    "context_lines": _canon(
                        to_ranks(text, fx.rank).splitlines())}
    return out


def _rebuild(entities: list[Any]) -> list[Any]:
    """Entities with canonically ordered one-hop context, for stable text."""
    for e in entities:
        e.neighbors = _canon(e.neighbors)
        e.sources = _canon(e.sources)
    return entities


def run_cases(reader: Any, fx: Fixture) -> dict[str, Any]:
    """Run every golden case against ``reader`` and return normalised output."""
    rank, i = fx.rank, fx.ids
    out: dict[str, Any] = {}
    out["get_entity"] = {k: to_ranks(reader.get_entity(i[k]), rank)
                         for k in _GET_KEYS}
    out["get_entity"]["missing"] = reader.get_entity(_GHOST)
    out["find_entities"] = _find_cases(reader, rank)
    out["neighbors"] = {k: _canon(to_ranks(reader.neighbors(i[k]), rank))
                        for k in _NEIGHBOR_KEYS}
    out["neighbors"]["missing"] = reader.neighbors(_GHOST)
    out["all_relationships"] = _canon(to_ranks(reader.all_relationships(), rank))
    out["provenance"] = {k: _canon(reader.provenance(i[k]))
                         for k in _PROVENANCE_KEYS}
    out["count_by_relationship"] = {
        "|".join(c): reader.count_by_relationship(c[0], c[1], c[2], c[3])
        for c in _COUNT_CASES}
    out["shortest_path"] = _path_cases(reader, fx)
    out["ask"] = _ask_cases(reader, fx)
    return out
