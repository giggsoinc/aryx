<p align="center">
  <img src="docs/aryx-logo.png" alt="Aryx" width="160" />
</p>

# Aryx Lite

**Point Aryx at your data. Get a deduplicated, linked knowledge graph you can ask questions of — with provenance on every answer.**

[![CI](https://github.com/giggsoinc/aryx/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/giggsoinc/aryx/actions/workflows/ci.yml)
[![License: BSL 1.1](https://img.shields.io/badge/license-BSL%201.1-blue.svg)](LICENSE)
[![Graph: FalkorDB](https://img.shields.io/badge/graph-FalkorDB-red.svg)](https://github.com/FalkorDB/FalkorDB)
[![Docker](https://img.shields.io/badge/docker-giggsodocker%2Faryx--lite-blue.svg)](https://hub.docker.com/r/giggsodocker/aryx-lite)
[![Docker Web](https://img.shields.io/badge/docker-aryx--lite--web-blue.svg)](https://hub.docker.com/r/giggsodocker/aryx-lite-web)

[Install](docs/INSTALL.md) · [Docker Hub](docs/DOCKERHUB.md) · [User guide](docs/USER_GUIDE.md) · [Quickstart data](examples/quickstart/) · [Contributing](CONTRIBUTING.md) · [Raven (Claude Code)](docs/RAVEN.md) · [Code of conduct](CODE_OF_CONDUCT.md) · [Licensing](docs/LICENSING.md)

> **Public · source-available (BSL 1.1).** Postgres is the system of record; the live knowledge graph is projected into **[FalkorDB](https://github.com/FalkorDB/FalkorDB)**.

---

## Repository overview

**Aryx** turns the data you already have into a **workspace-scoped knowledge graph** you can ask questions of. You state goals in plain English, connect a database or upload files, approve the model Aryx proposes, resolve duplicates into golden entities, and explore with **Ask**, **Model**, **Data** (tree / table / entity graph), and **Accuracy Lab** — with **provenance** on answers and merges.

| | |
|---|---|
| **Edition in this repo** | **Aryx Lite** — single-team outcome mapping (laptop / small server) |
| **Not (yet)** | Multi-tenant governed enterprise estate (that path is Enterprise / Aryx-o) |
| **SoT / graph** | PostgreSQL truth · FalkorDB rebuildable projection |
| **UI** | Next.js only (`apps/web`) — no Streamlit |
| **Images (public)** | [`giggsodocker/aryx-lite`](https://hub.docker.com/r/giggsodocker/aryx-lite) (API · worker · MCP) · [`giggsodocker/aryx-lite-web`](https://hub.docker.com/r/giggsodocker/aryx-lite-web) (Next.js UI) |
| **Tags** | `1.5.3` · `v1.5.3` · git short SHA (same tags on both images — always an explicit version, no `latest`) |
| **License** | BSL 1.1 → GPL-3.0-or-later on 2029-07-15 · [details](docs/LICENSING.md) |
| **Docker Hub overview** | [docs/DOCKERHUB.md](docs/DOCKERHUB.md) · [aryx-lite](https://hub.docker.com/r/giggsodocker/aryx-lite) · [aryx-lite-web](https://hub.docker.com/r/giggsodocker/aryx-lite-web) |

---

## What it does

| Step | What happens |
|------|----------------|
| **1. Brief** | You describe what you want to figure out in plain English — five grounding questions (domain, aim, objectives, scope, roles) steer every extraction |
| **2. Ingest** | Connect a database or upload files (CSV, PDF, DOCX, …) |
| **3. Resolve** | Duplicates merge into golden entities; weak pairs wait for human review |
| **4. Link** | Cross-file relationships are discovered and projected into a graph |
| **5. Explore** | Ask, Model canvas, Data explorer (tree / table / **entity graph**), Accuracy Lab |

Built for a **single team’s** outcome mapping on a laptop or small server — not yet a multi-tenant governed enterprise estate.

---

## Quick start

**Requirements:** [Docker](https://docs.docker.com/get-docker/) + Docker Compose · ~8 GB RAM recommended (Ollama models)

**Images (Docker Hub, public — no login to pull):**

| Image | Role | Tags |
|-------|------|------|
| [`giggsodocker/aryx-lite`](https://hub.docker.com/r/giggsodocker/aryx-lite) | API · worker · MCP | `1.5.3` · `v1.5.3` · `<sha>` |
| [`giggsodocker/aryx-lite-web`](https://hub.docker.com/r/giggsodocker/aryx-lite-web) | Next.js UI | same tags |

```bash
git clone https://github.com/giggsoinc/aryx.git
cd aryx
cp .env.example .env          # edit passwords / LLM keys as needed
docker compose pull           # pulls public Hub images (no docker login)
docker compose up -d          # builds from source only if pull/build policy requires it
```

First boot pulls LLM models into Ollama (can take several minutes).

| Surface | URL |
|---------|-----|
| **Web UI** | http://localhost:3000 |
| **Settings** (LLM provider / API keys) | http://localhost:3000/settings |
| **API docs** | http://localhost:8088/docs |
| **MCP (SSE)** | http://localhost:8765/sse |

Then: the home page lists your workspaces — **New workspace** walks you through Brief (drop a doc, confirm six drafted answers) → sources → run.

**Sample data:** upload the CSVs in [`examples/quickstart/`](examples/quickstart/) (customers + tickets) to exercise multi-file ingest and the entity graph.

Full steps, ports, and troubleshooting: **[docs/INSTALL.md](docs/INSTALL.md)** · Hub copy: **[docs/DOCKERHUB.md](docs/DOCKERHUB.md)** · UI walkthrough: **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**

### Smoke check (API)

```bash
curl -s http://localhost:8088/health
# then open http://localhost:3000
```

### Pull pinned images

```bash
docker pull giggsodocker/aryx-lite:1.5.3
docker pull giggsodocker/aryx-lite-web:1.5.3
# or v1.5.3 / git short SHA
```

---

## Product surfaces (Next.js)

| Route | Purpose |
|-------|---------|
| `/` | **Home** — workspace list with vitals; blank slate lands in the wizard |
| `/ask` | **Ask** — grounded Q&A with citations |
| `/start` | Guided onboard wizard — step 1 is the cruise-control Brief |
| `/brief` | **Brief** — revisit/edit the six grounding questions; doc upload + AI draft |
| `/model` | Ontology canvas (types, relationships, survivorship, axioms) |
| `/data` | Transparency explorer — Tree, Table, **interactive entity Graph** |
| `/lab` | Accuracy Lab — ontology ON vs OFF + reasoner check |
| `/settings` | **LLM provider** — Ollama, Anthropic, OpenAI-compatible, Gemini, Grok (xAI) |

There is **no Streamlit UI**. The product UI is Next.js only.

---

## Highlights

- **Brief-grounded extraction** — six questions (domain · aim · objectives · scope · roles · proof questions) steer the ontology; AI-drafted from your documents (PDF/DOC/PPT) or one sentence
- **Multi-source ingest** — Postgres, MySQL, Oracle; files (CSV/JSON/PDF/DOCX/PPTX/images)
- **Discovery-driven ontology** — propose types, human approval gate, RDF/OWL import-export
- **Entity resolution** — multi-key blocking, four-band scoring, HITL review, survivorship policies
- **Cross-file relationships** — deterministic FK discovery after multi-file upload
- **Entity graph** — pan/zoom, search, type filters, click-to-explore neighbors + detail panel
- **Workspace isolation** — LIST-partitioned Postgres; one graph per workspace
- **Local or cloud LLMs** — default Ollama; swap live under Settings (no restart)
- **MCP** — tools over SSE for external agents
- **Ports & adapters** — relational / graph / vector / LLM / reasoner / compute swappable for Enterprise / Aryx-o

---

## Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI + OpenAPI |
| Web | Next.js 15 (App Router, Tailwind) |
| Database (source of truth) | PostgreSQL 16 + pgvector |
| **Graph projection** | **[FalkorDB](https://github.com/FalkorDB/FalkorDB)** (one named graph per workspace) |
| LLM | Ollama (default) · Anthropic · OpenAI-compatible · Gemini · Grok — single broker, sequential pipeline (see [LLM architecture](#llm-architecture--how-the-agents-actually-work)) |
| External agent access | MCP over SSE (Aryx as tool provider) |
| Deploy | Docker Compose · [`giggsodocker/aryx-lite`](https://hub.docker.com/r/giggsodocker/aryx-lite) |

Aryx is an application on top of FalkorDB (and Postgres), not a fork of the database.

---

## LLM architecture — how the agents actually work

Aryx is **not** a multi-agent framework with autonomous agents negotiating over messages. It is a **single provider-agnostic Model Broker** feeding a **deterministic, sequential pipeline** — each stage calls one narrowly-scoped, stateless LLM function ("agent" in the classic sense: one job, one prompt, one schema) at a fixed point in the pipeline. No agent-to-agent (A2A) protocol, no hub-and-spoke coordinator, no agents calling other agents. Being precise about this matters: it's what makes ingestion auditable, replayable, and provider-swappable without touching orchestration logic.

**Pattern: single-broker pipeline (assembly line), not multi-agent orchestration.**

```
Ingest → [Discover] → [Resolve] → [Relate] → [Link] → [Project] → Done
             │            │           │
        extract_mentions  adjudicate  infer_relationship
         (cheap tier)    (frontier)    (frontier)
```

Each bracket is a fixed pipeline stage (`pipeline/orchestrate.py`); each stage below it calls exactly one stateless "agent" function through the broker, gets back structured JSON, and hands control to the next stage. No agent decides what runs next — the pipeline does.

### The Model Broker (`aryx/broker/`)

One provider-agnostic dispatch layer every agent calls through — never a direct SDK call from agent code:

| Provider | Dispatch |
|---|---|
| `ollama` | native Ollama `/api/chat` |
| `anthropic` | Claude SDK |
| anything else (`openai`, `gemini`, `grok`, `openrouter`, `vllm`, `lmstudio`, …) | OpenAI-compatible HTTP `/chat/completions` |

The broker resolves a **tier** (`frontier` → `mid` → `cheap` → `local`) to a concrete model, meters tokens per tier via `TokenGovernor`, and downgrades tiers on budget exhaustion — callers ask for a tier, never a model name. On quota/5xx/connection failures from a cloud provider, `aryx/llm.py` transparently falls back to the local Ollama model (loud log line, never silent); auth failures (401/403) do **not** fall back, so a bad key surfaces instead of being masked by a weaker model.

### The agents — one job, one prompt, one schema, no memory

| Agent | File | Tier | Classification | Job |
|---|---|---|---|---|
| **Schema mapper** | `pipeline/schema_agent.py` | frontier | Structured classifier | DB tables → ontology types + keys + relationships, from a plain-English goal |
| **Field tagger** | `pipeline/tag.py` | cheap | Structured classifier | Profiled columns → semantic type tags |
| **Ontology mapper** | `ontology/mapping.py` | frontier | Structured classifier | Source dataset → entity type + field mappings; proposes new types |
| **Entity extractor** | `ontology/extract.py` | cheap | Extraction agent + deterministic gate | Document chunks → entity mentions; a **non-LLM verbatim-span check** rejects any mention whose name isn't actually in its cited source text |
| **Adjudicator** | `resolution/adjudicate.py` | frontier | Binary classifier | Ambiguous-confidence record pair → same-entity yes/no |
| **Relationship namer** | `relationships.py` | frontier | Structured classifier | Two resolved entities → related? + directed relationship name |
| **Brief drafter** | `brief_draft.py` | frontier | Generative (schema-constrained) | Seed sentence / document → the 6-field workspace Brief |
| **Ontology assistant** | `ontology_assist.py` | frontier | Generative (schema-constrained) | Brief + type name → suggested attributes |
| **Correction-chat parser** | `api/corrections_api.py` | cheap | Intent classifier | Plain-language utterance → structured correction proposal (never applies directly — see below) |

None of these agents hold conversation state, call each other, or call tools mid-reasoning. Each is a pure function: `(structured input, prompt, schema) → structured output`. That statelessness is deliberate — it's what makes every stage independently retryable, swappable across providers, and safe to run behind a fallback.

### The one place a "propose → human approves → apply" loop exists

The correction-chat parser is the sole agent whose output is **never applied automatically**. It classifies an utterance into a proposed correction (retype, merge, link, unlink, remove, rename-type); the *human* clicks Apply; only then does a plain, non-LLM function mutate Postgres and re-project the graph. This is intentionally the opposite of autonomous multi-agent action — the LLM proposes, a human disposes, and the applied action is the resolved structure the user saw, not the raw model output. Every applied correction is stored as a standing rule and replayed as steering context into every future ingest — corrections *compound*, they don't need re-teaching.

### MCP — the actual multi-agent surface, and it's external, not internal

Aryx exposes ingestion, ontology, and HITL-question tools over MCP/SSE (`aryx/mcp/`) so **external** agents (Claude Code, Claude Desktop, any MCP client) can drive Aryx as a tool. This is the only point where "another agent" touches Aryx, and it's a client-server tool-call relationship, not peer-to-peer — Aryx is the tool provider, never the caller.

---

## Documentation

| Doc | Contents |
|-----|----------|
| [Install](docs/INSTALL.md) | Docker, Hub images, env, security, updates, local dev |
| [User guide](docs/USER_GUIDE.md) | Workspaces, onboard, Ask, Data, Model, Lab, Settings |
| [Quickstart data](examples/quickstart/) | Sample CSVs for multi-file upload → graph |
| [Features](docs/FEATURES.md) | Capability matrix |
| [Architecture](docs/ARCHITECTURE.md) | System design |
| [Licensing](docs/LICENSING.md) | BSL plain English |
| [Ingestion](docs/INGESTION_GUIDE.md) | Deep ingest walkthrough |
| [Docker Hub overview](docs/DOCKERHUB.md) | Image description (API / worker / MCP) |
| [Raven](docs/RAVEN.md) | Optional Claude Code workflow (`.claude` + manifest) |
| [Benchmarks](docs/wiki/BENCHMARKS.md) | ER measurements |

Diagrams: [Business view](docs/diagrams/business-view.html) · [Technical flow](docs/diagrams/technical-flow.html)

---

## Community

- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Issues](https://github.com/giggsoinc/aryx/issues) · [Discussions](https://github.com/giggsoinc/aryx/discussions) (if enabled)

---

## License (BSL 1.1)

Source-available under the **Business Source License 1.1**. You may use and modify Aryx Lite for evaluation, research, and internal production under the Additional Use Grant. Competing multi-tenant hosting of this work requires a commercial license until the Change Date (**2029-07-15**), when this version becomes **GPL-3.0-or-later**.

Full text: [`LICENSE`](LICENSE) · Summary: [`docs/LICENSING.md`](docs/LICENSING.md) · Notice: [`NOTICE`](NOTICE)

---

## Who builds it

Maintained by **[Giggso](https://giggso.com)**.
