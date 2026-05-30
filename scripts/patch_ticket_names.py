"""Patch SupportTicket entity names in FalkorDB (one-off demo seed)."""
from falkordb import FalkorDB

TICKET_NAMES = {
    6:  "T-001: API integration failing [OPEN]",
    7:  "T-002: Data sync delay [IN_PROGRESS]",
    8:  "T-003: Billing discrepancy [RESOLVED]",
    9:  "T-004: Data export timeout [ESCALATED]",
    10: "T-005: Permission denied on API [OPEN]",
    11: "T-006: Onboarding stuck [OPEN]",
    12: "T-007: SSO configuration error [IN_PROGRESS]",
}

g = FalkorDB(host="falkordb", port=6379).select_graph("aryx")

for eid, name in TICKET_NAMES.items():
    g.query("MATCH (e:Entity {id: $id}) SET e.name = $name", {"id": eid, "name": name})
    print(f"  entity {eid} -> {name}")

print("Done.")
