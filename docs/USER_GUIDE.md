# User Guide

## Overview

Aryx is built around **workspaces** — isolated projects with their own data, graph, and LLM settings. Start with the default workspace or create new ones for different use cases (Customer Support, Sales, BoM).

## Main Navigation

Open http://localhost:8501 and you'll see the sidebar:

- **Home** — Overview of active workspace, quick stats
- **Ingest** — Add data from databases or documents
- **Ask** — Query the knowledge graph in natural language
- **Graph** — Interactive visualization; drill-down to entity details
- **Ontology** — Browse, approve, import/export entity types
- **Observability** — Job history, LLM tokens/latency, graph stats
- **Settings** — Switch workspace, configure LLM provider

## Workspace Management

### Switch or Create Workspace

1. **Sidebar:** Click workspace dropdown (top left)
2. **Manage workspaces** button
3. **New workspace** — type name, click "Create"
4. **Delete** button removes workspace + all data (instant physical purge via LIST partition drop)

One workspace per project to keep data isolated. Default workspace is protected.

### Survivorship Policies

Each workspace has a survivorship policy that controls how duplicate records merge:

1. Go to **Settings** → **Survivorship** (or `GET /workspaces/{id}/survivorship`)
2. Choose a default strategy:
   - **first_non_empty** — first member's value wins (legacy default)
   - **source_priority** — ranked source list; highest-priority source wins
   - **most_recent** — newest `cleaned_at` timestamp wins
   - **most_complete** — member with most non-empty fields wins
   - **most_frequent** — modal value across members wins
3. Override per attribute (e.g., `revenue` uses `most_recent` while default is `source_priority`)
4. Save — applies to all future resolution runs in this workspace

All strategies except `first_non_empty` are order-independent: shuffling input members produces the same golden record.

When multiple sources disagree on an attribute, the system logs a **conflict row** with the winning value, losing values, strategy used, and contributing record IDs. View conflicts in the entity detail panel or via `GET /admin/entities/{id}`.

## Ingestion Workflow

### Database Path

1. Go to **Ingest tab** → **Database (auto-discover)** tab
2. **Step 1 — What are you building?**
   - Provide crisp context (e.g., *"Customer accounts Q2 2026: include names, company, industry, deal size"*)
   - Or upload a context file (TXT/PDF/DOCX with entity description)
3. **Step 2 — Connect**
   - Fill RDBMS (postgresql, mysql, etc.), host, port, database, user, password
   - Click **"Connect & introspect"** — system reads table schema
4. **Step 3 — Auto-discover**
   - Agent maps tables to entity types using your context
   - Click **"Run discovery agent"**
5. **Step 4 — Review & ingest**
   - Edit proposed entity types / match keys as needed
   - Click **"Ingest selected tables"** → job starts
   - Watch progress in **Ingestion progress** panel below

### Document Path

1. Go to **Ingest tab** → **Documents (folder)** tab
2. **Step 1** — Provide context (text or upload file)
3. **Step 2** — Drop files (JSON, CSV, PDF, PPTX, DOCX, images); max 50 files, 2 MB each
4. Click **"Read & discover"** → system extracts text, finds entities
5. Review results → tick entity types to keep → **"Confirm & add to graph"**

## Entity Resolution

After ingest, the resolution pipeline runs automatically:

1. **Blocking** — Groups records by shared keys (prefix, token overlap, phonetic). Only records in the same block are compared.
2. **Scoring** — Cheap LLM scores pairwise similarity (0 to 1).
3. **Routing** — Pairs are routed to one of four bands:
   - **Auto-merge** (>=0.92) — merged without human input
   - **Adjudicate** (0.90-0.92) — frontier LLM decides
   - **Review** (0.75-0.90) — queued for human steward
   - **Reject** (<0.75) — not a match
4. **Clustering** — Transitive closure of merge decisions forms entity clusters.
5. **Golden record** — Survivorship policy merges member attributes into one canonical record.

Each entity receives a **confidence score** = weakest merge-edge in its cluster, clamped between 0.5 and 0.99. Human-approved edges score 0.99. Singletons (no merges) score 0.5.

## Adjudication Queue

Pairs in the review band (0.75-0.90) are queued for human decision.

### Reviewing Pairs

1. **API:** `GET /adjudication?status=pending&page=1&size=20`
2. Each item shows the two records, their similarity score, and attributes side-by-side
3. **Decide:** `POST /adjudication/{id}/decide` with `{"decision": "approve"}` or `{"decision": "reject"}`
4. Approved pairs merge their entities; rejected pairs stay separate
5. Every decision (approve or reject) persists as labeled training data

### Stats

`GET /adjudication/stats` returns:
- Total pending, approved, rejected counts
- Human/LLM agreement rate (when both have decided on overlapping pairs)

## Actions (Kinetic Layer)

Actions are declarative mutations — a JSON definition that describes what to change, under what conditions, with human approval.

### Defining Actions

```json
{
  "name": "upgrade_tier",
  "version": 1,
  "guard": {"attribute": "revenue", "op": ">=", "value": 1000000},
  "params": ["new_tier"],
  "effects": [
    {"kind": "set_attribute", "target": "self", "attribute": "tier", "value": "{new_tier}"}
  ]
}
```

- **guard** — Condition checked against the target entity; reuses the rules engine
- **params** — Required input parameters (validated before execution)
- **effects** — Operations to apply: `set_attribute`, `add_relationship`, `remove_relationship`, etc.

### Executing Actions

1. `POST /actions/{name}/execute` with params + target entity
2. System checks guard → validates params → creates execution record
3. If auto-apply mode: effects apply immediately with before/after audit log
4. If MCP-initiated: execution is **always-pending** until a human approves via `POST /actions/executions/{id}/decide`

### MCP `act` Tool

External AI agents can request actions via the MCP `act` tool. These are never auto-applied — a human must approve each execution via the API.

## Querying the Graph

### Ask Tab

1. Go to **Ask tab**
2. Type a natural-language question:
   - *"Which customers are associated with product X?"*
   - *"Find all support tickets from acme.com"*
   - *"Show me high-value deals closed in the last 30 days"*
3. Each response shows the answer, source records with links, and token count/latency

Ask follows conversation context — reference earlier messages ("What about the accounts I just mentioned?").

### Graph Tab

1. Go to **Graph tab**
2. **Search** — find entities by name, type, or property
3. **Type filter** — show only Person, Company, Product, etc.
4. **Click node** → drill-down: properties, neighbors, provenance, confidence score
5. **Path queries** — shortest path between any two entities

## Ontology Management

### Browse & Approve

The Ontology tab shows proposed and approved entity types:

- **Proposed** — Types discovered during ingest or imported from OWL/Turtle; require human approval
- **Approved** — Active types in the ontology; shown as `owl:Class` with instance counts and attributes
- **Relationships** — Listed as `owl:ObjectProperty` with counts

### Import External Ontology

1. Go to **Ontology** → **Import** tab
2. Upload a vocabulary file (TTL, OWL, RDF/XML, JSON-LD, N-Triples)
3. Classes become **proposed** types that pass through the approval gate

### Export

Export the current ontology as Turtle, JSON-LD, or RDF/XML for use in external tools (Protege, SPARQL endpoints, data lakes).

## Observability

- **Job list** — all ingest jobs with status, progress, timestamps
- **LLM tokens** — cumulative usage across providers (cost tracking)
- **Graph stats** — entity count, relationship count, last projection timestamp
- **Stage checkpoints** — per-stage status for each pipeline run; resume failed runs via `POST /jobs/{id}/resume`

## Settings

### LLM Provider

1. Go to **Settings tab**
2. **Active provider** dropdown: Local (Ollama), Claude, OpenAI, Gemini
3. Paste API key (if not Local) → click **"Set & test"**
4. Change takes effect immediately for future queries

## Tips

- **Context is critical** — "Customer data" is too vague; "Customer accounts Q2: names, company, deal amount" works
- **Provenance** — Every entity traces back to source records; trust the chain
- **Confidence** — Entities near 0.5 are singletons or weak merges; entities near 0.99 had human approval
- **Local + Cloud hybrid** — Use Ollama for cheap stages; pay for Claude only on hard decisions
- **Workspace per project** — Customers vs. Sales vs. Products deserve separate graphs
- **Resume, don't restart** — Failed pipelines resume from the last checkpoint; use `POST /jobs/{id}/resume`

## Next Steps

- [Install Guide](INSTALL.md) — Get running locally or on EC2
- [Feature Matrix](FEATURES.md) — All capabilities at a glance
- [Architecture](ARCHITECTURE.md) — How Aryx works under the hood
- [Ingestion Guide](INGESTION_GUIDE.md) — Detailed ingest walkthrough
