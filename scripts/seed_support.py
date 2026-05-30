"""Seed HAS_TICKET relationships between companies and support ticket entities."""
from falkordb import FalkorDB

g = FalkorDB(host="falkordb", port=6379).select_graph("aryx")

links = [
    (1, 6), (1, 7),
    (2, 8),
    (4, 9), (4, 10),
    (3, 11),
    (5, 12),
]
for company_id, ticket_id in links:
    g.query(
        "MATCH (a:Entity {id: $src}), (b:Entity {id: $tgt}) "
        "MERGE (a)-[:REL {name: $name}]->(b)",
        {"src": company_id, "tgt": ticket_id, "name": "HAS_TICKET"},
    )
    print(f"  linked entity {company_id} -> entity {ticket_id}")

rows = g.query("MATCH (a)-[r:REL]->(b) RETURN a.name, r.name, b.name").result_set
print(f"\nTotal relationships in graph: {len(rows)}")
for r in rows:
    print(f"  {r[0]} --[{r[1]}]--> {r[2]}")
