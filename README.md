# Aryx Lite — a lightweight ontology layer for quick outcome mapping

> **This repo is Aryx Lite (v1)** — the fast, approachable front door:
> point it at your data, and in minutes you have a deduplicated, linked
> knowledge graph you can ask questions of. Bundled Postgres + FalkorDB +
> Ollama; built for a single team's quick outcome mapping, not yet a
> governed enterprise estate.
>
> **Editions:** **Aryx Lite** (v1, this repo — **BSL 1.1**) ·
> **Aryx Enterprise** (v2 — scale, governance, sovereignty, the Accuracy
> Lab · commercial) · **Aryx-o** (v2.1 — Enterprise native on Oracle ADB
> and other hyperscalers · commercial). See [docs/EDITIONS.md](docs/EDITIONS.md)
> and [docs/LICENSING.md](docs/LICENSING.md).

**Aryx** ingests records from databases and documents, resolves duplicates across sources into single entities, infers relationships, and builds a searchable knowledge graph. Use it to reason over messy, multi-source data — customers from Postgres and Salesforce, support tickets from email and Jira, products from inventory and e-commerce — all deduplicated and linked in one place.

## Features

### Web App (primary UI)
- **Next.js 15 web app** (`apps/web/`) — primary UI, talks to the API only over HTTP. Surfaces: **Ask** (`/`), **Model** (`/model`), **Data** (`/data`), **Lab** (`/lab`), **Onboard** (`/start`), **Settings** (`/settings` — LLM provider / keys: Ollama, Anthropic, OpenAI-compatible, Gemini, Grok).
- **Accuracy Lab** (`/lab`) — runs the same model with the ontology ON vs OFF, side-by-side, with a groundedness scorecard and citations traced to source records; plus a read-only reasoner-check.
- **Data Explorer** (`/data`) — three lenses: Tree (types → entities → provenance), Table (records grid + provenance drawer), Graph (type-level knowledge map). Every record traceable to `system.dataset#record`.

### Ingest & Discovery
- **Multi-source ingest** — Postgres, MySQL, Oracle connectors; CSV/PDF/DOCX/PPTX/JSON file upload
- **Auto-discovery** — AI agent maps source schemas to entity types; no upfront ontology required
- **Ontology HITL gate** — Proposed types queue for human approval; OWL/Turtle/JSON-LD import + RDF export
- **Streaming pipeline** — One-record-at-a-time extract → land → tag → map (memory-bounded at any scale)

### Entity Resolution
- **Multi-key blocking** — Prefix + token-set + Soundex keys with block-size cap (G2)
- **Four-band adjudication** — Auto-merge (>=0.92), LLM-adjudicate (0.90-0.92), human-review (0.75-0.90), reject (<0.75); thresholds from measured sweep
- **Human-in-the-loop queue** — Ambiguous pairs queue for steward review; every decision persists as labeled training data (data moat)
- **Survivorship policies** — Five strategies (first-non-empty, source-priority, most-recent, most-complete, most-frequent) with per-attribute overrides and conflict audit trail
- **Cluster confidence** — Weakest merge-edge score, clamped [0.5, 0.99]; human edges score 0.99; entities never claim 1.0
- **Chunked resolution** — 3-pass streaming (key → score → cluster) for datasets that exceed memory; memory bound = largest block
- **Stage checkpoints** — Pipeline stages track running/done/failed; crashed runs resume from last completed stage

### Knowledge Graph
- **Interactive graph** — FalkorDB projection with entity drill-down, neighbor traversal, shortest-path queries
- **Incremental projection** — Dirty-set watermark computation; auto-selects full or incremental mode (<30% dirty = incremental)
- **Provenance threads** — Every entity traces back to source records across all contributing systems

### Intelligence
- **Chat (Ask)** — Natural-language queries with LLM reasoning, source provenance, and conversation context
- **MCP integration** — 21 tools (workspace / brief / datasource / ingest / ontology / ask / act) for external AI agents; SSE transport
- **Actions (kinetic layer)** — Declarative JSON DSL mutations with guard conditions, human approval gate, and before/after audit log; agent-initiated actions are always-pending

### Platform
- **Editions** — Aryx Lite (v1) / Enterprise (v2) / Aryx-o (v2.1, Oracle ADB native); see [docs/EDITIONS.md](docs/EDITIONS.md)
- **Ports & adapters seam** (`aryx.ports`) — 6 capability ports (Relational, Graph, Vector, LLM, Reasoner, Compute) with config-driven adapters, so the substrate is swappable (the Oracle-readiness foundation)
- **Workspace isolation** — LIST-partitioned Postgres tables; independent graphs, ontologies, and policies per workspace
- **Local + cloud models** — Ollama for cheap stages (tagging, scoring); Claude/OpenAI/Gemini for frontier decisions (~1-5% of volume)
- **API-key auth** — Off/optional/required modes; fail-closed (exceptions reject, never pass)
- **Connection pooling** — psycopg3 shared pool singleton; all 10 stores pooled
- **27 idempotent migrations** — Auto-apply on API startup; zero manual migration steps
- **Measured quality** — `make er-bench` on Febrl1: P=1.00 / R=0.59 / F1=0.74; band thresholds derived from measured sweep, not opinion

## Quick Start

```bash
git clone https://github.com/giggsoinc/aryx.git
cd aryx
docker compose up -d
# Web UI:  http://localhost:3000
# Settings: http://localhost:3000/settings  (LLM provider / API keys)
# API:     http://localhost:8088/docs
# MCP SSE: http://localhost:8765/sse
```

First time? Open the web UI → create a workspace → land on the **`/start`** wizard: set your goals → add a source (connect a database or upload a file) → run. Configure Gemini/Grok/OpenAI/Ollama under **Settings**.

## Documentation

| Guide | What it covers |
|-------|---------------|
| **[Install Guide](docs/INSTALL.md)** | Local Docker setup, EC2 deployment, git-only update flow, tuning env keys |
| **[User Guide](docs/USER_GUIDE.md)** | UI walkthrough, ingest, Ask, Graph, adjudication queue, actions, survivorship |
| **[Feature Matrix](docs/FEATURES.md)** | All capabilities with status and component references |
| **[Architecture](docs/ARCHITECTURE.md)** | System design, resolution funnel, data flow, API routers, MCP tools |
| **[Ingestion Guide](docs/INGESTION_GUIDE.md)** | Database and document ingest step-by-step |
| **[RDF Export](docs/RDF_EXPORT_GUIDE.md)** | Export to SPARQL, semantic web tools, LLM pipelines |
| **[Benchmarks](docs/wiki/BENCHMARKS.md)** | Append-only P/R/F1 measurements |
| **[Program Close](docs/wiki/PROGRAM_CLOSE.md)** | Gap-closure decisions (DEC-001..006), v2 backlog |

**Interactive diagrams:** [Business View](docs/diagrams/business-view.html) | [Technical Flow](docs/diagrams/technical-flow.html)

## Stack

| Layer | Tech |
|-------|------|
| **API** | FastAPI (27 routers, OpenAPI docs) |
| **Web UI** | Next.js 15 (App Router, Tailwind) |
| **Database** | PostgreSQL 16 + pgvector (source of truth, LIST-partitioned by `workspace_id`) |
| **Graph** | FalkorDB (one named graph per workspace, `aryx_ws_<id>`) |
| **LLM** | Ollama (local) + Anthropic / OpenAI / Gemini (frontier, runtime-swappable) |
| **Agent protocol** | MCP — 21 tools over SSE |
| **Deployment** | Docker Compose (local + EC2) |
| **UI** | Next.js (`apps/web`) — Settings for live LLM provider/key |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md) (Raven discipline).

## License

**Business Source License 1.1 (BSL 1.1)** — source-available, not OSI open source.

| | |
|---|---|
| **Licensor** | Giggso Inc. |
| **You may** | Use, modify, and run Aryx Lite for evaluation, research, and **internal production** |
| **You may not** | Offer Aryx Lite (or a derivative) as a **competing multi-tenant / hosted product** without a commercial license |
| **Change Date** | 2029-07-15 — then this version becomes **GPL-3.0-or-later** |
| **Commercial** | [licensing@giggso.com](mailto:licensing@giggso.com) |

Full legal text: [`LICENSE`](LICENSE) · Plain English: [`docs/LICENSING.md`](docs/LICENSING.md) · Copyright notice: [`NOTICE`](NOTICE)

> BSL is not Apache/MIT. It is designed so teams can adopt Aryx freely, while
> commercial re-hosting of a competing service requires a paid license.
