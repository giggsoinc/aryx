# Architecture

## System Overview

Aryx is a knowledge graph platform that ingests records from heterogeneous sources (databases, files), resolves duplicate records into single entities, infers relationships, and builds a queryable graph.

**Core principle:** Postgres is the source of truth; FalkorDB is a rebuildable projection. Cheap, deterministic stages (blocking, scoring) shrink the search space so frontier LLMs only touch the hard ~1–5% of decisions.

## Architecture Diagrams

### 1. Business View (What Users See)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                    📊 ARYX PLATFORM                   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
    ┌───▼─────┐          ┌────▼────┐          ┌───▼─────┐
    │📥 INGEST│          │💬 ASK   │          │📊 GRAPH │
    │         │          │         │          │         │
    │Database │          │Natural  │          │Visual   │
    │Documents│          │Language │          │Explorer │
    └─┬───────┘          └──┬─────┘           └──┬──────┘
      │                      │                   │
      │ [Context +           │ [Question]        │ [Drill-down]
      │  Data] ✓             │ ✓                 │
      │                      │                   │
      ├──────────────────────┼───────────────────┤
      │                                          │
      ▼                                          ▼
   [BACKEND PIPELINE]          [BACKEND PIPELINE]
   • Extract & Land             • Search & Query
   • Auto-discover types        • LLM reasoning
   • Merge duplicates           • Source tracking
   • Build relationships        
   • Project to graph           
      │                                          │
      └──────────────────────┬───────────────────┘
                             │
                    ┏━━━━━━━━▼━━━━━━━┓
                    ┃ 🗄️ KNOWLEDGE   ┃
                    ┃   GRAPH        ┃
                    ┃                ┃
                    ┃ Entities       ┃
                    ┃ Relationships  ┃
                    ┃ Provenance     ┃
                    ┗━━━━━━━━━━━━━━━━┛
```

**Business Flow Explanation:**
- **Ingest path:** User provides context (who/what is this data?) + connects source → system auto-discovers entity types, merges duplicates, builds graph
- **Ask path:** User asks natural-language question → LLM retrieves relevant entities from graph, reasons, returns answer with source links
- **Graph path:** User explores entities visually → drill down to relationships, provenance, linked records

---

### 2. Technical Flow (System Architecture)

```
┌─────────────────────────────────────────────────────────────────┐
│                        🖥️  USER INTERFACE LAYER                 │
├─────────────────────────────────────────────────────────────────┤
│  📱 Streamlit UI (8501)  │  🔌 REST API / FastAPI (8088)        │
│  - Home, Ingest, Ask     │  - /entities, /ask, /ingest          │
│  - Graph, Settings       │  - /jobs, /graph, /workspaces        │
└──────────┬───────────────┴───────────┬──────────────────────────┘
           │                           │
           └─────────────┬─────────────┘
                         │
┌─────────────────────────▼──────────────────────────────────────┐
│                    ⚙️  ORCHESTRATION LAYER                      │
├─────────────────┬─────────────────┬──────────────┬──────────────┤
│  Pipeline       │  LLM Broker     │  Job Queue   │  Workspace   │
│  Orchestrate    │  (Tier routing) │  (async)     │  Manager     │
│  • Extract      │  • Local        │              │              │
│  • Land         │  • Cheap        │              │              │
│  • Tag          │  • Frontier     │              │              │
│  • Resolve      │                 │              │              │
│  • Project      │                 │              │              │
└────┬────────────┼────────┬────────┴──────────────┴──────────────┘
     │            │        │
     │    ┌───────▼────────▼──────┐
     │    │   🧠 MODEL LAYER      │
     │    ├───────────────────────┤
     │    │ • Ollama (local)      │
     │    │ • Claude API          │
     │    │ • OpenAI compatible   │
     │    │ • Embeddings service  │
     │    └───────────────────────┘
     │
┌────▼──────────────────────────────────────────────────────────┐
│              💾 DATA STORAGE LAYER                             │
├──────────────────────────┬──────────────────────────────────┤
│  🗄️  Postgres            │  📊 FalkorDB (Graph)             │
│  (Source of Truth)       │  (Rebuildable Projection)        │
│                          │                                  │
│  • aryx_entity           │  • Named graph per workspace    │
│  • aryx_relationship     │  • Entities (nodes)             │
│  • aryx_landed_record    │  • Relationships (edges)        │
│  • aryx_entity_member    │  • Provenance threads          │
│  • aryx_job              │                                 │
│  • workspace (isolated   │  ↑ Wipe & rebuild safe         │
│    via LIST partitions)  │    (data in Postgres)          │
└──────────────────────────┴──────────────────────────────────┘
```

**Technical Flow Explanation:**
1. **User Interface** — Streamlit (UI) and FastAPI (API) accept user requests
2. **Orchestration** — Pipeline runs the 7-stage ingest; LLM Broker routes queries to appropriate model tier; Job Queue manages async work
3. **Models** — Local Ollama (tagging, scoring), frontier APIs (Claude for hard decisions)
4. **Storage** — Postgres = source of truth (all records, provenance, workspace isolation); FalkorDB = interactive graph (rebuilt from Postgres as needed)

## Data Flow Pipeline (7-Stage Ingest)

```
    SOURCE DATA
    (Database, Files, Documents)
           │
           ▼
    ┌──────────────────┐
    │ 1️⃣  EXTRACT      │
    ├──────────────────┤
    │ Connectors read  │
    │ stream 1 record  │
    │ at a time        │
    │ (memory safe)    │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ 2️⃣  LAND         │
    ├──────────────────┤
    │ Store raw record │
    │ in Postgres      │
    │ + provenance     │
    │ (source tracking)│
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ 3️⃣  TAG          │
    ├──────────────────┤
    │ Cheap AI (Ollama)│
    │ labels fields    │
    │ (email, phone,   │
    │  date, currency) │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ 4️⃣  MAP          │
    ├──────────────────┤
    │ Agent maps       │
    │ table → entity   │
    │ type (Person,    │
    │ Company, etc.)   │
    │ HITL gate        │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ 5️⃣  RESOLVE      │
    ├──────────────────┤
    │ a) Block         │
    │    (group by     │
    │     exact match) │
    │ b) Score        │
    │    (cheap model) │
    │ c) Adjudicate    │
    │    (frontier LLM │
    │     on 1-5%      │
    │     ambiguous)   │
    │ d) Cluster      │
    │    (merge into   │
    │     entities)    │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ 6️⃣  RELATE       │
    ├──────────────────┤
    │ Infer edges      │
    │ • FKs (fast)     │
    │ • Co-occurrence  │
    │ • LLM (opt.)     │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ 7️⃣  PROJECT      │
    ├──────────────────┤
    │ Build interactive│
    │ graph in FalkorDB│
    │ (rebuildable)    │
    └────────┬─────────┘
             │
             ▼
         📊 GRAPH
    (Queryable, Explorable)
```

**Stage Details:**

| Stage | What | Why | Cost |
|-------|------|-----|------|
| **1. Extract** | Read from source (DB, files) | Stream 1 record at a time | Free (connectors) |
| **2. Land** | Store raw + provenance | Track where data came from | Postgres writes |
| **3. Tag** | Semantic field labels | Cheap AI understands field types | Ollama (local, free) |
| **4. Map** | Source → entity types | Human + AI agree on ontology | Frontier LLM (expensive) |
| **5. Resolve** | Find & merge duplicates | Clean data → single entities | Mix cheap + frontier |
| **6. Relate** | Infer entity→entity edges | Link entities via FK or meaning | Deterministic + optional LLM |
| **7. Project** | Build FalkorDB graph | Interactive visualization | FalkorDB writes |

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
