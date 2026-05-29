"""Seed demo data: fix entity names in FalkorDB + add sample relationships.

Run on the server after deploy:
  python scripts/seed_demo.py
"""
from __future__ import annotations

import os
import sys

from falkordb import FalkorDB

GRAPH_URL = os.environ.get("ARYX_GRAPH_URL", "redis://localhost:6379")
GRAPH_NAME = "aryx"

NAMES = {
    1: "Acme Corp",
    2: "Globex LLC",
    3: "Initech",
    4: "Umbrella Co",
    5: "Stark Industries",
}

RELATIONSHIPS = [
    (2, 1, "SUPPLIES"),
    (5, 3, "ACQUIRED"),
    (4, 2, "PARTNERS_WITH"),
    (1, 4, "COMPETES_WITH"),
]

from urllib.parse import urlparse

parsed = urlparse(GRAPH_URL)
db = FalkorDB(host=parsed.hostname or "localhost", port=parsed.port or 6379)
g = db.select_graph(GRAPH_NAME)

print("Fixing entity names...")
for eid, name in NAMES.items():
    g.query("MATCH (e:Entity {id: $id}) SET e.name = $name", {"id": eid, "name": name})
    print(f"  {eid} → {name}")

print("Adding relationships...")
for src, tgt, rel in RELATIONSHIPS:
    g.query(
        "MATCH (a:Entity {id: $src}), (b:Entity {id: $tgt}) "
        "MERGE (a)-[:REL {name: $name}]->(b)",
        {"src": src, "tgt": tgt, "name": rel},
    )
    print(f"  {NAMES[src]} --[{rel}]--> {NAMES[tgt]}")

print("Verifying...")
rows = g.query("MATCH (e:Entity) RETURN e.id, e.name ORDER BY e.id").result_set
for r in rows:
    print(f"  entity {r[0]}: {r[1]}")

rel_rows = g.query("MATCH (a)-[r:REL]->(b) RETURN a.name, r.name, b.name").result_set
for r in rel_rows:
    print(f"  {r[0]} --[{r[1]}]--> {r[2]}")

print("Done.")
