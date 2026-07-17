# Docker Hub — Aryx Lite images

Public images under **[giggsodocker](https://hub.docker.com/u/giggsodocker)** (no login required to pull).

| Image | Role | Hub |
|-------|------|-----|
| **`giggsodocker/aryx-lite`** | Python runtime: **API**, **worker**, **MCP** (same image, different commands) | [hub.docker.com/r/giggsodocker/aryx-lite](https://hub.docker.com/r/giggsodocker/aryx-lite) |
| **`giggsodocker/aryx-lite-web`** | **Next.js** product UI | [hub.docker.com/r/giggsodocker/aryx-lite-web](https://hub.docker.com/r/giggsodocker/aryx-lite-web) |

Source: [github.com/giggsoinc/aryx](https://github.com/giggsoinc/aryx) · License: **BSL 1.1** → GPL-3.0-or-later on **2029-07-15**

---

## Repository overview (product)

**Aryx Lite** turns the data you already have into a **workspace-scoped knowledge graph** you can ask questions of — with **provenance** on answers and merges.

| | |
|---|---|
| **Edition** | Aryx Lite — single-team outcome mapping (laptop / small server) |
| **System of record** | PostgreSQL 16 (+ pgvector) |
| **Graph projection** | [FalkorDB](https://github.com/FalkorDB/FalkorDB) (rebuildable; never sole truth) |
| **UI** | Next.js only — no Streamlit |
| **Default LLM** | Ollama (local); Settings also supports Anthropic, OpenAI-compatible, Gemini, Grok |

### What the stack does

1. **Goals** — describe outcomes in plain English  
2. **Ingest** — Postgres / MySQL / Oracle or files (CSV, JSON, PDF, DOCX, …)  
3. **Resolve** — multi-key blocking, four-band scoring, HITL review, survivorship  
4. **Link** — cross-file relationships → workspace graph  
5. **Explore** — Ask (cited answers), Model canvas, Data explorer (tree / table / entity graph), Accuracy Lab  

---

## Tags (both images)

Tags are kept in sync when maintainers run `./scripts/docker-hub-publish.sh`.

| Tag | Meaning |
|-----|---------|
| `latest` | Current release build |
| `1.0.0` | Semver (matches `aryx.__version__` / `pyproject.toml`) |
| `v1.0.0` | Same release, `v`-prefixed |
| `<git-sha>` | Exact commit (e.g. `a98a954`) |

```bash
# Backend (API / worker / MCP)
docker pull giggsodocker/aryx-lite:latest
docker pull giggsodocker/aryx-lite:1.0.0
docker pull giggsodocker/aryx-lite:v1.0.0

# Web UI
docker pull giggsodocker/aryx-lite-web:latest
docker pull giggsodocker/aryx-lite-web:1.0.0
docker pull giggsodocker/aryx-lite-web:v1.0.0
```

---

## Quick start (full stack)

Prefer Compose from the source repo (Postgres, FalkorDB, Ollama, API, worker, MCP, web):

```bash
git clone https://github.com/giggsoinc/aryx.git
cd aryx
cp .env.example .env
docker compose pull    # public Hub images — no docker login required
docker compose up -d
```

| Surface | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API / OpenAPI | http://localhost:8088/docs |
| MCP (SSE) | http://localhost:8765/sse |

Pin versions:

```bash
export ARYX_IMAGE=giggsodocker/aryx-lite:1.0.0
export ARYX_WEB_IMAGE=giggsodocker/aryx-lite-web:1.0.0
docker compose up -d
```

---

## Image-specific notes

### `aryx-lite` (this is the backend image)

- One image, three roles via command: **api**, **worker**, **mcp**
- Needs Postgres + FalkorDB (+ LLM) for a working stack
- Does **not** include the browser UI

### `aryx-lite-web`

- Next.js UI; talks HTTP only (same-origin `/api` proxy to the API)
- Pair with `aryx-lite` + Postgres + FalkorDB + LLM for a full product experience

---

## Architecture (short)

- **Postgres** = source of truth (entities, relationships, provenance, checkpoints)  
- **FalkorDB** = rebuildable graph projection (one named graph per workspace)  
- **Ports & adapters** seam for Lite / Enterprise / Aryx-o substrate swaps  

---

## Docs

- [Install](https://github.com/giggsoinc/aryx/blob/main/docs/INSTALL.md)  
- [User guide](https://github.com/giggsoinc/aryx/blob/main/docs/USER_GUIDE.md)  
- [Architecture](https://github.com/giggsoinc/aryx/blob/main/docs/ARCHITECTURE.md)  
- [Licensing](https://github.com/giggsoinc/aryx/blob/main/docs/LICENSING.md)  

### Platform note

Images published from Apple Silicon are **linux/arm64** unless a multi-arch build is published. Use a matching host or build from source on `amd64`.

### Maintainer

[Giggso](https://giggso.com) · Commercial licensing: licensing@giggso.com  
Source & issues: [giggsoinc/aryx](https://github.com/giggsoinc/aryx)
