# Architecture

## System Overview

Aryx is a knowledge graph platform that ingests records from heterogeneous sources (databases, files), resolves duplicate records into single entities, infers relationships, and builds a queryable graph.

**Core principle:** Postgres is the source of truth; FalkorDB is a rebuildable projection. Cheap, deterministic stages (blocking, scoring) shrink the search space so frontier LLMs only touch the hard ~1–5% of decisions.

## Component Architecture (C4)

```
┌─────────────────────────────────────────────────────────┐
│                      Users / Applications               │
├─────────────────┬───────────────────────────────────────┤
│   Streamlit UI  │        REST API (FastAPI)             │
│  (localhost:    │      (localhost:8088)                  │
│    8501)        │  GET /entities, /graph                │
│                 │  POST /ask, /ingest                   │
└────────┬────────┴──────────┬───────────────────────────┘
         │                   │
    ┌────┴─────────────────┬─┴─────────────────┐
    │                      │                   │
┌───▼──────┐      ┌────────▼────────┐   ┌─────▼──────┐
│  Pipeline │      │   LLM Broker    │   │ Job Queue  │
│  Orchestrate    │  (route by tier) │   │  (async)   │
└───┬──────┘      └────┬────────┬───┘   └──────┬─────┘
    │                 │        │              │
    │    ┌────────────┴┐       │              │
    │    │   Models    │       │              │
    ▼    │  ┌─────────┐│       │              │
┌────────────┤Ollama   │◄──────┴──────┐       │
│  Connectors│(local)  │              │       │
│            │└─────────┤              │       │
│  ┌────────┐│┌─────────┴─┐           │       │
│  │Postgres├┤Claude API  │           │       │
│  │extractor││(frontier)  │           │       │
│  └────────┘│└───────────┘           │       │
│            │┌─────────┐              │       │
│  ┌───────┐ │OpenAI    │              │       │
│  │ Files │ │Compatible│              │       │
│  │extract│ └──────────┘              │       │
│  └───────┘└────────────────┐         │       │
└────────────────────────────┼─────────┼───────┤
                             │         │       │
                    ┌────────┘  ┌──────┴──┐    │
                    │           │         │    │
                ┌───▼────────────▼──┐  ┌─▼────▼───┐
                │    Postgres       │  │ FalkorDB  │
                │  (source truth)   │  │  (graph   │
                │  - entities       │  │  projection)
                │  - relationships  │  │           │
                │  - provenance     │  └───────────┘
                │  - artifacts      │
                └───────────────────┘
```

## Data Flow Pipeline

### Stages

```
1. EXTRACT
   Connectors read from sources (Postgres, file uploads)
   → stream rows one at a time (memory-bounded)

2. LAND
   Records land in Postgres with provenance (source_system, record_id)

3. TAG
   Cheap model (Ollama) applies semantic field tags
   (email, phone, date, currency, etc.)

4. ONTOLOGY MAP (frontier LLM)
   Agent maps source tables → canonical entity types
   Agent maps fields → canonical attributes
   HITL gate: human approves new types

5. RESOLUTION
   a) BLOCK: Deterministic grouping (name match, email match)
   b) SCORE: Cheap model scores pairs (0.0–1.0 likelihood of match)
   c) ADJUDICATE: Frontier LLM on ambiguous ~5% (0.4–0.6 confidence)
   d) CLUSTER: UnionFind transitive closure → entity IDs

6. RELATIONSHIP INFER
   FK constraints → deterministic entity→entity edges
   Co-occurrence + optional LLM → implied relationships

7. PROJECT
   Write entities + relationships to FalkorDB (named graph per workspace)
   Preserve provenance threads (trace any graph node back to source)
```

## Key Components

### Connectors (pluggable readers)

- **PostgresConnector** — JDBC-style, reads tables streaming
- **FileConnector** — CSV, JSON, PDF, PPTX, DOCX, images
- Protocol: `extract() -> Iterator[Record]`

### Pipeline Spine

- **run_spine()** — streaming transform: extract → clean → profile → land
- One record at a time (no full-dataset load)
- Cheap tagging + blocking happens as records flow through

### Store (Postgres)

- **aryx_entity** — canonical entities (id, type, properties)
- **aryx_relationship** — edges (source_id, target_id, type, properties)
- **aryx_landed_record** — raw landed records (provenance link)
- **aryx_entity_member** — which records resolved into each entity
- **aryx_ontology** — type + field catalog
- All tables **LIST-PARTITIONED** by workspace_id for isolation + physical purge

### LLM Broker (provider-agnostic routing)

- **Registry** — ModelSpec by Tier (local/cheap/frontier)
- **Governor** — token budget, rate-limiting
- Supports: Ollama (local), Anthropic Claude, OpenAI, OpenAI-compatible
- **Secrets** — AWS Secrets Manager / SSM Parameter Store

### FalkorDB Projection

- One **named graph** per workspace (ws_1, ws_2, etc.)
- Nodes: entities (id, type, name)
- Edges: relationships (type, properties)
- Provenance threads: trace any node back to source records
- Wipe-and-rebuild safe: Postgres has the real data

## Technology Stack

| Layer | Tech | Why |
|---|---|---|
| **Language** | Python 3.13 | Type safety + async; SQL in .sql files (DB-Guard) |
| **API** | FastAPI | Async routes; auto-OpenAPI docs; Pydantic validation |
| **UI** | Streamlit | Rapid prototyping; live updates without JS |
| **Database** | Postgres 16 | ACID, full-text search, partitioning, JSON |
| **Graph** | FalkorDB | Fast traversal; easy to wipe/rebuild |
| **Local LLM** | Ollama | Private data; offline; 0-cost inference (cheap stages) |
| **Cloud LLM** | Anthropic, OpenAI | Frontier tier (hard decisions only) |
| **Deployment** | Docker Compose | Reproducible, works local + EC2 + K8s |
| **IaC** | Terraform (planned) | AWS infrastructure versioning |

## Architectural Decisions

| Decision | Rationale | Date |
|---|---|---|
| Postgres source of truth; FalkorDB rebuildable | Graph can be wiped anytime; no graph-only state | 2026-05-28 |
| Streaming one-record-at-a-time | Code path serves small tables + TB datasets; memory-bounded | 2026-05-28 |
| Resolution funnel (block → score → adjudicate) | Cheap/deterministic layers shrink search space; ration frontier spend | 2026-05-28 |
| Provider-agnostic Broker | Decouple from vendor lock-in | 2026-05-28 |
| Ollama embeddings locally | Anthropic has no API; keeps private data on-box | 2026-05-28 |
| HITL gate for new ontology types | Nothing untraceable; human decisions become training labels | 2026-05-28 |
| Workspaces + LIST partitioning | Instant isolation + physical purge | 2026-05-28 |

## Scaling Notes

- **10x data:** Streaming pipeline stays memory-bounded; Postgres partitioning + FalkorDB indexing scale to 100M entities
- **10x users:** REST API scales horizontally (stateless); Postgres connection pooling; async IO bounds
- **10x models:** Broker routes by tier; Ollama queue manages parallel inference; frontier costs stay ~1–5% via funnel

## Security

- **Secrets:** AWS Secrets Manager / SSM Parameter Store (never in code)
- **SQL injection:** Parameterized queries via SQLAlchemy ORM + SQL files
- **Data isolation:** Workspace LIST partitioning; delete cascade on workspace removal
- **Access:** API basic auth (placeholder); Streamlit session-based
- **Audit:** Job table logs all ingest + LLM calls with provenance

## Next Steps

- [Install Guide](INSTALL.md) — Get running locally
- [User Guide](USER_GUIDE.md) — Navigate the UI
- [Ingestion Guide](INGESTION_GUIDE.md) — Deep-dive on pipeline stages
