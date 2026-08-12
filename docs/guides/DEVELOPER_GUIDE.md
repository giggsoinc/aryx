# Aryx Lite — Developer & Agent Engineer Guide

**Audience:** AI engineers, agent developers, backend/platform engineers, knowledge-graph engineers, technical architects  
**Edition:** Aryx Lite (this repository / self-host stack)  
**Version:** 1.7.x

---

## What is Aryx Lite?

**Aryx** is a **self-building context layer for AI agents**.

Aryx Lite is the **self-hostable** product you run on a laptop or small server: connect databases and files, discover entities and relationships, resolve identity across sources, project a **context / knowledge graph** with provenance, then **serve** that context to apps and agents via **REST**, **Ask**, and **MCP**.

Under the hood you will recognize familiar pieces (entity resolution, graph projection, GraphRAG-style grounded answers, ontology discovery). Those are **implementation**. The product outcome is:

> **Give AI agents connected business context without hand-building and constantly re-maintaining a full semantic model for every domain.**

| Aryx Lite is | Aryx Lite is not |
|--------------|------------------|
| A context engine you run next to your data | A replacement for Postgres or your warehouse |
| Identity + links + provenance for agents | “Just another vector DB” |
| Discover → resolve → graph → serve | A pure academic ontology studio |
| Docker-first full stack + Python API | Zero-ops SaaS (that’s commercial hosting) |

**Stack (Lite):** Postgres (system of record) · FalkorDB (graph projection) · FastAPI · Next.js UI · Ollama or cloud LLMs · MCP SSE.

---

## Why it is critical (developer point of view)

### The problem you actually hit

Agents and LLM apps can **call tools and retrieve docs**. They still fail when:

1. The same customer is `C-991` in CRM, `ACME-US` in ERP, and free text in a ticket.  
2. Every agent re-infers joins inside the prompt.  
3. RAG returns the right PDF paragraph but **not** the path: customer → contract → product → open incident.  
4. You cannot show **which source record** justified an answer.  
5. Each new agent (support, sales ops, finance) reimplements the same glue.

### What breaks without a context layer

| Pattern | Failure mode |
|---------|----------------|
| Bigger context windows | Still no stable entity IDs across systems |
| More RAG | Relevant chunks ≠ connected facts |
| Hand-written tools only | Tools return rows; agents still invent relationships |
| Per-agent memory | Memory is personal; **business identity is not shared** |

### Why Aryx Lite matters to *you*

- **Ship agent features faster** — context is a service, not a side project in every repo.  
- **Shared workspace graph** — multiple agents and apps hit the same resolved entities.  
- **MCP-native** — Claude Desktop, Claude Code, and other MCP hosts can drive Aryx as tools.  
- **HTTP-native** — your FastAPI/Next/LangGraph app can Ask or query without owning ER.  
- **Provenance** — you can debug and audit what the model was grounded on.  
- **Data-first setup** — sample files/DB → smart plan → build; less “empty ontology form” work.

> **Retrieval finds information. Aryx connects meaning.**

---

## How to get started

### Requirements

- Docker + Docker Compose  
- ~8 GB RAM if using local Ollama models  
- Optional: cloud LLM API key (Gemini, OpenAI, Anthropic, Grok) in **Settings**

### Install (recommended)

```bash
git clone https://github.com/giggsoinc/aryx.git
cd aryx
cp .env.example .env
docker compose pull
docker compose up -d
```

| Surface | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API OpenAPI | http://localhost:8088/docs |
| MCP SSE | http://localhost:8765/sse |
| Health | `curl -s http://localhost:8088/health` |

Images: `giggsodocker/aryx-lite` · `giggsodocker/aryx-lite-web` (see [DOCKERHUB.md](../DOCKERHUB.md)).

### First technical success path

1. **Settings** — confirm LLM (Ollama list or cloud samples).  
2. **New workspace** — setup is **data first**.  
3. Upload [`examples/quickstart/`](../../examples/quickstart/) `customers.csv` + `tickets.csv`.  
4. **Smart review** — approve brief + graph plan → **Build**.  
5. **Data** — entities + provenance; **Model** — types; **Ask** — grounded Q&A.  
6. Optional: point Claude Desktop MCP at `http://localhost:8765/sse` ([mcp-guide.html](../mcp-guide.html)).

> **Note:** Full product today is **Compose-first**. A pure `pip install aryx-lite` “one wheel = entire stack” path is roadmap packaging; the Python package in-repo is the API/engine, not Postgres+UI by itself.

---

## How to use (by developer stakeholder)

### AI / agent engineer

| Goal | How |
|------|-----|
| Ground answers | UI **Ask**, or HTTP Ask endpoints (OpenAPI) |
| Give Claude tools | MCP host → Aryx SSE tools (workspaces, ingest status, ask-style flows) |
| Avoid prompt-side ER | Ingest CRM+ticket files once; query resolved entities |
| Iterate models | Settings / Home model gate — provider-agnostic |

**Design tip:** Treat Aryx as **context infrastructure**. Your agent orchestrator stays thin: plan → call Aryx/MCP → act.

### Backend / app developer

| Goal | How |
|------|-----|
| Product feature “explain this account” | Backend calls Aryx Ask or entity APIs; your UI renders citations |
| Multi-tenant-ish isolation | Use **workspaces** (one graph partition per use case) |
| Jobs / ops | **Observe** + Jobs chip; resume from checkpoint when `run_id` is set |
| CI demo | Compose + sample CSVs + health check |

### Data / platform engineer

| Goal | How |
|------|-----|
| Source systems | Connect Postgres/MySQL/Oracle or upload files |
| Identity quality | Match keys, HITL adjudication, Correct data coach |
| Graph health | Observe vitals, Falkor projection, re-ingest / reset workspace data |
| Config | `ARYX_RDB_DSN`, `ARYX_GRAPH_URL`, `ARYX_LLM_*` in `.env` |

### Knowledge graph / ontology engineer

| Goal | How |
|------|-----|
| Inspect types | **Model** canvas |
| Import/export | RDF/OWL paths ([RDF_EXPORT_GUIDE.md](../RDF_EXPORT_GUIDE.md)) |
| Don’t start blank | Prefer discovery + smart plan; refine types after load |
| Lab | Accuracy Lab ontology ON vs OFF |

---

## Interfaces cheat sheet

```text
Humans          →  Web UI :3000
Your apps       →  REST  :8088  (OpenAPI)
Claude / MCP    →  MCP SSE :8765
Ops             →  Observe, Jobs, docker logs
```

| Channel | Use when |
|---------|----------|
| **MCP** | Coding agents and Claude-family hosts should *operate* Aryx — product menu **MCP** (`/mcp`) has copy-paste config |
| **REST** | Production backends and custom agent frameworks |
| **UI** | Domain review, demos, smart setup, Correct data |
| **CLI** (partial) | Pipeline/ops scripts; evolving toward fuller product CLI |

---

## Mental model

```text
Sources → Discover → Resolve → Project graph → Serve (Ask / API / MCP)
              ↑                    │
              └──── provenance ────┘
```

Postgres holds truth (landed records, entities, jobs).  
FalkorDB is a **rebuildable projection** agents can traverse.  
That is intentional—not a claim of zero-copy live federation of every SaaS API.

---

## Further reading

| Doc | Why |
|-----|-----|
| [USER_GUIDE.md](../USER_GUIDE.md) | Full UI walkthrough |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Ports, adapters, design |
| [INGESTION_GUIDE.md](../INGESTION_GUIDE.md) | Pipeline stages |
| [FEATURES.md](../FEATURES.md) | Capability matrix |
| [EDITIONS.md](../EDITIONS.md) | Lite vs Enterprise |
| [BUSINESS_GUIDE.md](BUSINESS_GUIDE.md) | Same product, business lens |
| HTML twin | [DEVELOPER_GUIDE.html](DEVELOPER_GUIDE.html) |

---

*Aryx Lite — self-building context for agents. Retrieval finds information; Aryx connects meaning.*
