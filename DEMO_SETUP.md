# Support Demo Setup — Radio Equipment Support Case

## Phase 1: Schema + Routes (COMPLETED ✅)

Files created:
- `migrations/002_support_demo_schema.sql` — PostgreSQL DDL (11 tables, 11 indices)
- `src/aryx/demo/support_data_generator.py` — Synthetic data generator (200 tickets, 150 devices, 15 agents)
- `src/aryx/api/demo_ingest_api.py` — FastAPI routes (`/api/demo/load`, `/api/demo/tickets`, `/api/demo/agents`, `/api/demo/resolutions`)
- `src/aryx/api/main.py` — Updated to include demo router
- `scripts/load_demo_data.sh` — Schema loader (shell)
- `scripts/load_demo_via_api.py` — Demo data loader (Python)

## Deployment Steps (EC2)

### 1. Apply the Schema

```bash
# SSH to EC2
ssh -i ~/.ssh/rvdts-oracle-key.pem ec2-user@ec2-3-91-73-197.compute-1.amazonaws.com

# Navigate to project
cd /path/to/Aryx

# Set DB credentials (or they're already in ARYX_RDB_DSN env var)
export PGPASSWORD="your_postgres_password"

# Apply the schema
psql -h localhost -p 5432 -U aryx -d aryx -f migrations/002_support_demo_schema.sql
```

### 2. Start Aryx API Server

```bash
# Ensure ARYX_RDB_DSN is set
export ARYX_RDB_DSN="postgresql://aryx:password@localhost:5432/aryx"

# Start the server
python3 -m uvicorn aryx.api.main:app --host 0.0.0.0 --port 8000
```

### 3. Load Demo Data

**Option A: Via curl**
```bash
curl -X POST http://localhost:8000/api/demo/load \
  -H 'Content-Type: application/json' \
  -d '{"ticket_count": 200, "clean_first": true}'
```

**Option B: Via Python script**
```bash
python3 scripts/load_demo_via_api.py --api-url http://localhost:8000 --tickets 200
```

### 4. Verify Data Loaded

```bash
# Query endpoints
curl http://localhost:8000/api/demo/tickets?status=open | jq .
curl http://localhost:8000/api/demo/agents?level=L3 | jq .
```

## Data Schema Overview

**6 Core Tables:**
- `support_customers` (10 rows) — Network operators (SLA tiers: bronze → platinum)
- `support_sites` (20 rows) — Physical locations (HQ/Remote/Mobile)
- `support_devices` (150 rows) — Radio equipment (models, firmware, status)
- `support_agents` (15 rows) — Support staff (L1/L2/L3 + expertise)
- `support_tickets` (200 rows) — Problem reports (status, priority, symptom)
- `support_resolutions` (120 rows) — Solutions applied (firmware, config, RMA)

**Many-to-Many:**
- `support_ticket_device_links` (300 rows) — Ticket → Device mapping (affected/root_cause/witness)
- `support_agent_expertise` — Agent → Expertise tag mapping

## Aryx Onboarding Workflow (Tomorrow)

```
1. Brief          → Define domain competency questions (5 Q's)
2. Ingest         → Point Aryx at the 6 tables + sample queries
3. ASK            → Run pre-canned queries
   - "Show me open critical tickets"
   - "Escalations to L3"
   - "Unresolved tickets by agent"
4. Graph          → Entity triples (agent:hasExpertise, device:runsFirmware, ticket:escalatedTo)
5. Ontology       → Export as RDF
6. Observability  → Metrics dashboard (escalation rate, MTTR, utilization)
```

## Realistic Data Characteristics

- **Symptom text:** Radio terminology (signal loss, firmware crashes, interference, thermal shutdown)
- **Escalation logic:** 35–70% of critical tickets escalate to L2/L3
- **Time distribution:** Tickets span 90 days with realistic resolution times (2–48 hours)
- **Device diversity:** 10 radio models with 6 firmware versions
- **Agent specialization:** L3 engineers specialize in Firmware/Hardware, L1 handles General support

## Next Steps

1. ✅ Deploy schema to EC2 Postgres
2. ✅ Load demo data via API
3. 🔲 Design Brief screen UI (make it less "shit brick")
4. 🔲 Prepare ASK queries for demo
5. 🔲 Validate Graph entity extraction
6. 🔲 Test RDF export
