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

**Aryx** turns the data you already have into a **workspace-scoped knowledge graph** you can ask questions of. **Load data first** — Aryx samples it with your Settings model (any provider), drafts the brief and a multi-type graph plan, you approve lightly, then resolve/link/explore with **Ask**, **Model**, **Data**, and **Accuracy Lab** — with **provenance** on every answer.

| | |
|---|---|
| **Edition in this repo** | **Aryx Lite 1.7** — data-first smart setup · single-team outcome mapping |
| **Enterprise** | Separate commercial fork — agentic ontology planning, EDA control plane (extends same data-first story) |
| **Not in Lite** | Multi-tenant governance, Stage-2 multi-agent ontology fleet, A2A mesh |
| **SoT / graph** | PostgreSQL truth · FalkorDB rebuildable projection |
| **UI** | Next.js only (`apps/web`) — no Streamlit |
| **Images (public)** | [`giggsodocker/aryx-lite`](https://hub.docker.com/r/giggsodocker/aryx-lite) · [`giggsodocker/aryx-lite-web`](https://hub.docker.com/r/giggsodocker/aryx-lite-web) |
| **Tags** | `1.7.0` · `v1.7.0` · git short SHA (always an explicit version, no `latest`) |
| **License** | BSL 1.1 → GPL-3.0-or-later on 2029-07-15 · [details](docs/LICENSING.md) |
| **Product flow (HTML)** | [docs/UI_BUSINESS_FLOW.html](docs/UI_BUSINESS_FLOW.html) |
| **Docker Hub** | [docs/DOCKERHUB.md](docs/DOCKERHUB.md) |

---

## What it does (Lite 1.7 — data first)

| Step | What happens |
|------|----------------|
| **1. Load data** | Setup: Files and/or Database — samples read before full graph build |
| **2. Smart review** | Answer model drafts **brief** + **graph plan** (e.g. Transaction + Merchant). Optional extra docs suggested |
| **3. Confirm & build** | Save brief → ingest steered by plan; dimensions + Model types seeded |
| **4. Resolve & link** | Duplicates merge; column/FK links; provenance kept |
| **5. Explore** | Data · Model · Lab · Ask · Observe · Correct data |

You do **not** invent six blank brief answers before Aryx has seen data. Edit the brief anytime on `/brief`.

Built for a **single team’s** outcome mapping on a laptop or small server — not yet a multi-tenant governed enterprise estate.

---

## Quick start

**Requirements:** [Docker](https://docs.docker.com/get-docker/) + Docker Compose · ~8 GB RAM recommended (Ollama models)

**Images (Docker Hub, public — no login to pull):**

| Image | Role | Tags |
|-------|------|------|
| [`giggsodocker/aryx-lite`](https://hub.docker.com/r/giggsodocker/aryx-lite) | API · worker · MCP | `1.7.0` · `v1.7.0` · `<sha>` |
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

Then: Home lists workspaces — **New workspace** → setup (**data first**): sources → upload/connect → **smart review** (brief + graph plan) → build.

**Sample data:** upload the CSVs in [`examples/quickstart/`](examples/quickstart/) (customers + tickets) to exercise multi-file ingest and the entity graph.

Full steps, ports, and troubleshooting: **[docs/INSTALL.md](docs/INSTALL.md)** · Hub copy: **[docs/DOCKERHUB.md](docs/DOCKERHUB.md)** · UI walkthrough: **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**

### Smoke check (API)

```bash
curl -s http://localhost:8088/health
# then open http://localhost:3000
```

### Pull pinned images

```bash
docker pull giggsodocker/aryx-lite:1.7.0
docker pull giggsodocker/aryx-lite-web:1.7.0
# or v1.7.0 / git short SHA
```

---

## Product surfaces (Next.js) — Lite 1.7.0

| Route | Purpose |
|-------|---------|
| `/` | **Home** — workspaces, model gate, create / open / reset / delete (non-Default) |
| `/start` | **Setup** — data first → smart review → build (empty workspaces land here) |
| `/brief` | **Brief** — edit anytime (usually drafted after data load) |
| `/data` | Tree / Table / Graph explorer + **Correct data** coach |
| `/model` | Ontology canvas (types, relationships, survivorship, axioms) |
| `/lab` | Accuracy Lab — ontology ON vs OFF + reasoner check |
| `/ask` | **Ask** — grounded Q&A with citations |
| `/observe` | Jobs, workspace vitals, storage truth |
| `/settings` | **LLM provider** — Ollama / cloud; powers smart understand + Ask |

There is **no Streamlit UI**. The product UI is Next.js only.

**Enterprise** (separate commercial fork) extends the same data-first setup with agentic EDA / Stage-2 planning — not part of this Lite tree. See [EDITIONS.md](docs/EDITIONS.md).

---

## Highlights

- **Data-first smart setup** — sample → drafted brief + multi-type graph plan (any Settings model) → approve → build
- **Brief-grounded extraction** — six questions after data understanding; editable anytime
- **Multi-source ingest** — Postgres, MySQL, Oracle; files (CSV/JSON/PDF/DOCX/PPTX/images)
- **Dimension entities** — e.g. Merchant / Category from columns when the plan says so
- **Discovery-driven ontology** — types seeded to Model; RDF/OWL import-export
- **Entity resolution** — multi-key blocking, four-band scoring, HITL review, survivorship policies
- **Cross-file relationships** — deterministic FK discovery after multi-file upload
- **Entity graph** — pan/zoom, search, type filters + Correct data selection
- **Workspace isolation** — LIST-partitioned Postgres; menu lists all workspaces; safe delete for non-Default
- **Local or cloud LLMs** — Ollama · Anthropic · OpenAI · Gemini · Grok — same understand path
- **MCP** — tools over SSE for external agents
- **Ports & adapters** — seam for Enterprise / Aryx-o substrate swaps

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
