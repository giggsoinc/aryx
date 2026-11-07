"""Deterministic graph fixture for the FalkorDB -> Postgres parity work.

Builds one isolated workspace whose data exercises every behaviour the graph
reader has to preserve: duplicate edges, dangling edges, self-loops, cycles,
parallel edges, display-name edge cases, a result set over the 500-row cap,
shared display names, and provenance fan-out.

Entity ids differ in every database, so everything is addressed by a logical
key and compared by *rank* (position in id order, which equals insertion
order in a fresh workspace). Used by scripts/capture_graph_golden.py and the
golden e2e test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Json

from aryx.models import EntityMember, Relationship, ResolvedEntity
from aryx.queries import load
from aryx.store.entity_store import EntityStore
from aryx.store.pool import get_pool
from aryx.workspaces import WorkspaceStore

BULK_COUNT = 520  # more than the reader's 500-row cap
_CLEANED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
_GHOST = 987654321  # an entity id that never exists (dangling edge target)

# (key, ontology_type, attributes)
_ENTITIES: list[tuple[str, str, dict[str, Any]]] = [
    ("acme1", "Customer", {"name": "Acme Corp", "city": "Paris"}),
    ("acme2", "Customer", {"name": "Acme Corp", "city": "Berlin"}),
    ("zoe", "Customer", {"name": "Zoë Ünïcode 日本"}),
    ("falsy0", "Customer", {"name": 0, "title": "Fallback Title"}),
    ("emptyname", "Customer", {"name": "", "label": "Lbl"}),
    ("emptylist", "Customer", {"name": [], "email": "a@b.co"}),
    ("booltrue", "Customer", {"name": True}),
    ("longonly", "Customer", {"note": "x" * 81}),
    ("keyorder", "Customer", {"zeta": "z-val", "alpha_key": "a-val"}),
    ("mixedcase", "Customer", {"name": "UPPER lower Mixed"}),
    ("wild", "Customer", {"name": "100% real_deal"}),
    ("lonely", "Customer", {"name": "Lonely"}),
    ("numcode", "Product", {"code": 123}),
    ("floatsku", "Product", {"sku": 1.5}),
    ("widget", "Product", {"sku": "SKU-1", "name": "Widget"}),
]
_TICKETS = 6
_CHAIN = 6
_NODE_KEYS = [f"n{i}" for i in range(1, _CHAIN + 1)]
_CYCLE = ["cyc1", "cyc2", "cyc3"]
_RING = ["sq1", "sq2", "sq3", "sq4"]  # 4-cycle: equal-length paths both ways


@dataclass
class Fixture:
    """What a built fixture exposes to capture and test code."""

    workspace_id: int
    dsn: str
    ids: dict[str, int] = field(default_factory=dict)
    rank: dict[int, int] = field(default_factory=dict)

    def key_rank(self) -> dict[str, int]:
        """Logical key -> rank, stable across databases."""
        return {k: self.rank[v] for k, v in self.ids.items()}


def _entity_rows() -> list[tuple[str, str, dict[str, Any]]]:
    rows = list(_ENTITIES)
    rows += [(f"t{i}", "Ticket", {"ticket_ref": f"T-{i}", "status": "open"})
             for i in range(1, _TICKETS + 1)]
    rows += [(k, "Node", {"name": k}) for k in _NODE_KEYS + _CYCLE + _RING + ["loopself"]]
    rows += [(f"bulk{i}", "Bulk", {"name": f"bulk-{i:04d}"})
             for i in range(BULK_COUNT)]
    return rows


def _seed_landed(dsn: str, ws: int) -> dict[str, int]:
    """Two runs of landed records; returns payload rid -> landed record id."""
    layout = [("crm", "customers", ["c-1", "c-2"]),
              ("erp", "accounts", ["a-1"]),
              ("helpdesk", "tickets", ["h-1", "h-2"])]
    pool = get_pool(dsn)
    out: dict[str, int] = {}
    with pool.connection() as conn:
        with conn.cursor() as cur:
            for system, dataset, rids in layout:
                cur.execute(load("insert_run"), (ws, system, dataset))
                run_id = int(cur.fetchone()[0])
                for rid in rids:
                    cur.execute(load("insert_landed_record"),
                                (ws, run_id, system, dataset, rid,
                                 Json({"rid": rid}), _CLEANED_AT))
                cur.execute(load("select_landed_by_run"), (run_id, ws))
                for record_id, payload, _sys, _at in cur.fetchall():
                    out[payload["rid"]] = int(record_id)
    return out


def _members_for(key: str, landed: dict[str, int]) -> list[EntityMember]:
    plan = {"acme1": ["c-1", "a-1"], "acme2": ["c-2"],
            "t1": ["h-1"], "t2": ["h-1", "h-1"],  # same record twice
            "t3": ["h-2"]}
    return [EntityMember(landed_record_id=landed[r]) for r in plan.get(key, [])]


def _edges(i: dict[str, int]) -> list[Relationship]:
    """All relationships, including the awkward ones, by logical key."""
    def rel(a: int, b: int, name: str) -> Relationship:
        return Relationship(source_entity_id=a, target_entity_id=b, name=name,
                            confidence=1.0)

    edges = [rel(i["t1"], i["acme1"], "raised_by"),
             rel(i["t1"], i["acme1"], "raised_by"),     # duplicate edge
             rel(i["t1"], i["acme1"], "mentions"),      # parallel, other name
             rel(i["t2"], i["acme1"], "raised_by"),
             rel(i["t3"], i["acme2"], "raised_by"),     # same display name
             rel(i["t4"], i["zoe"], "raised_by"),
             rel(i["t5"], i["widget"], "about"),
             rel(i["acme1"], _GHOST, "ghost"),          # dangling target
             rel(_GHOST, i["acme2"], "ghost"),          # dangling source
             rel(i["loopself"], i["loopself"], "self"),  # self-loop
             rel(i["acme1"], i["acme2"], "same_group")]
    chain = _NODE_KEYS
    edges += [rel(i[a], i[b], "next") for a, b in zip(chain, chain[1:])]
    edges += [rel(i["cyc1"], i["cyc2"], "loop"), rel(i["cyc2"], i["cyc3"], "loop"),
              rel(i["cyc3"], i["cyc1"], "loop")]
    edges += [rel(i[a], i[b], "ring")
              for a, b in zip(_RING, _RING[1:] + _RING[:1])]
    return edges


def build_fixture(dsn: str, name: str) -> Fixture:
    """Create the workspace and every entity, member and edge. Returns ids."""
    wstore = WorkspaceStore(dsn)
    try:
        ws = int(wstore.create(name)["id"])
    finally:
        wstore.close()
    landed = _seed_landed(dsn, ws)
    estore = EntityStore(dsn, ws)
    rows = _entity_rows()
    results = [(ResolvedEntity(ontology_type=t, attributes=a, confidence=1.0),
                _members_for(k, landed)) for k, t, a in rows]
    estore.save(results)
    listed = sorted(estore.list_entities(), key=lambda r: r[0])
    ids_in_order = [r[0] for r in listed]
    fx = Fixture(workspace_id=ws, dsn=dsn,
                 rank={eid: n for n, eid in enumerate(ids_in_order)})
    # entities were inserted in row order, so the n-th smallest id is row n
    fx.ids = {rows[n][0]: ids_in_order[n] for n in range(len(rows))}
    estore.save_relationships(_edges(fx.ids))
    return fx


_ID_PATTERNS = (r"\(id (\d+)\)", r"id=(\d+)", r"get_neighbors\((\d+)\)",
                r"get_provenance\((\d+)\)",
                r"(?<!\w)#(\d+)\b")  # fallback display name "#<entity id>"
_ID_KEYS = {"id", "source", "target"}


def _rank_text(text: str, rank: dict[int, int]) -> str:
    for pattern in _ID_PATTERNS:
        text = re.sub(pattern, lambda m: m.group(0).replace(
            m.group(1), str(rank.get(int(m.group(1)), int(m.group(1))))), text)
    return text


def to_ranks(obj: Any, rank: dict[int, int]) -> Any:
    """Replace entity ids with ranks throughout a reader result."""
    if isinstance(obj, dict):
        return {k: (rank.get(v, v) if k in _ID_KEYS and isinstance(v, int)
                    else to_ranks(v, rank)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_ranks(v, rank) for v in obj]
    if isinstance(obj, str):
        return _rank_text(obj, rank)
    return obj
