# Aryx Lite

**Point Aryx at your data. Get a deduplicated, linked knowledge graph you can ask questions of — with provenance on every answer.**

Aryx Lite is a **source-available (BSL 1.1)** knowledge-graph platform for a single team: ingest databases and files, resolve duplicates into golden entities, project a queryable graph, and answer questions with citations.

## Repository overview

| | |
|---|---|
| **Product** | Aryx Lite — outcome mapping → ontology → graph → grounded Ask |
| **Source** | [github.com/giggsoinc/aryx](https://github.com/giggsoinc/aryx) |
| **This image** | Python runtime: **API**, **worker**, and **MCP** (same image, different commands) |
| **Companion UI** | [`giggsodocker/aryx-lite-web`](https://hub.docker.com/r/giggsodocker/aryx-lite-web) (Next.js) |
| **System of record** | PostgreSQL 16 (+ pgvector) |
| **Graph projection** | [FalkorDB](https://github.com/FalkorDB/FalkorDB) (rebuildable; never sole truth) |
| **Default LLM** | Ollama (local); Settings also supports Anthropic, OpenAI-compatible, Gemini, Grok |
| **License** | Business Source License 1.1 → GPL-3.0-or-later on **2029-07-15** |

### What the stack does

1. **Goals** — describe outcomes in plain English  
2. **Ingest** — Postgres / MySQL / Oracle or files (CSV, JSON, PDF, DOCX, …)  
3. **Resolve** — multi-key blocking, four-band scoring, HITL review, survivorship  
4. **Link** — cross-file relationships → workspace graph  
5. **Explore** — Ask (cited answers), Model canvas, Data explorer (tree / table / entity graph), Accuracy Lab  

### Image tags

| Tag | Meaning |
|-----|---------|
| `latest` | Current release build |
| `1.0.0` / `v1.0.0` | Semver (matches `aryx.__version__`) |
| `<git-sha>` | Exact commit (e.g. `a98a954`) |

```bash
docker pull giggsodocker/aryx-lite:1.0.0
docker pull giggsodocker/aryx-lite:latest
```

### Quick start (full stack)

Prefer the Compose file in the source repo (Postgres, FalkorDB, Ollama, API, worker, MCP, web):

```bash
git clone https://github.com/giggsoinc/aryx.git
cd aryx
cp .env.example .env
docker compose pull    # uses giggsodocker/aryx-lite + aryx-lite-web when available
docker compose up -d
```

| Surface | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API / OpenAPI | http://localhost:8088/docs |
| MCP (SSE) | http://localhost:8765/sse |

This image alone is the **backend**. For a complete product experience, run Compose (or pair with `aryx-lite-web` + Postgres + FalkorDB + LLM).

### Architecture (short)

- **Postgres** = source of truth (entities, relationships, provenance, checkpoints)  
- **FalkorDB** = rebuildable graph projection (one named graph per workspace)  
- **Next.js UI** talks HTTP only (same-origin `/api` proxy) — no Python in the browser app  
- **Ports & adapters** seam for Lite / Enterprise / Aryx-o substrate swaps  

### Docs

- [Install](https://github.com/giggsoinc/aryx/blob/main/docs/INSTALL.md)  
- [User guide](https://github.com/giggsoinc/aryx/blob/main/docs/USER_GUIDE.md)  
- [Architecture](https://github.com/giggsoinc/aryx/blob/main/docs/ARCHITECTURE.md)  
- [Licensing](https://github.com/giggsoinc/aryx/blob/main/docs/LICENSING.md)  

### Platform note

Images published from Apple Silicon are **linux/arm64** unless a multi-arch build is published. Use a matching host or build from source on `amd64`.

### Maintainer

[Giggso](https://giggso.com) · Commercial licensing: licensing@giggso.com  
Source & issues: [giggsoinc/aryx](https://github.com/giggsoinc/aryx)
