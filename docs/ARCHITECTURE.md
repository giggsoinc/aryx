# Architecture

## System Overview

Aryx is a knowledge graph platform that ingests records from heterogeneous sources (databases, files), resolves duplicates into single entities, infers relationships, and builds a queryable graph.

**Core principle:** Postgres is the source of truth; FalkorDB is a rebuildable projection. Cheap, deterministic stages (blocking, scoring) shrink the search space so frontier LLMs only touch the hard ~1-5% of decisions.

## V2 Architecture (Web UI + Ports & Adapters)

Two structural changes define the current generation:

1. **The Next.js web app is the primary UI.** `apps/web/` is an isolated Next.js 15 deploy unit. It never imports Python or touches the database — it talks to the FastAPI API only over HTTP. The browser calls same-origin `/api/...`; the Next server rewrites those to the API via `next.config.mjs` (`source: "/api/:path*"` → `${ARYX_API_URL_INTERNAL || "http://api:8000"}/:path*`). Surfaces:

   | Route | Surface | Purpose |
   |-------|---------|---------|
   | `/` | **Ask** | NL question answering with grounded, cited answers |
   | `/model` | **Model** | Ontology / type model browser |
   | `/data` | **Data** | Data Explorer (summary, entities, graph) |
   | `/lab` | **Lab** | Accuracy Lab — ontology-on vs ontology-off A/B |
   | `/start` | **Onboard** | Guided workspace + source onboarding wizard |

   The **Streamlit** app (`src/aryx/ui/`) is **legacy** but still present and runnable.

2. **Ports & adapters (hexagonal) seam.** `src/aryx/ports/` introduces a substrate-swappable seam so the platform is not welded to Postgres/FalkorDB/Ollama:

   - `protocols.py` — capability-port contracts as `typing.Protocol`: `RelationalPort`, `GraphReaderPort`, `GraphStorePort`, `VectorPort`, `LlmPort`, `ReasonerPort`, `ComputePort`.
   - `config.py` — resolves each port to a `module:Class` target. Defaults (the **Lite** family) wrap today's shipped Postgres/FalkorDB/Ollama implementations; any port can be overridden per-environment via `ARYX_ADAPTER_*` env vars.
   - `container.py` — the composition root. Call-sites obtain dependencies through `ports()`, which imports and constructs the adapter bound to each port.
   - `src/aryx/edition.py` — the `ARYX_EDITION` flag (`lite` / `enterprise` / `aryx-o`). Enterprise unlocks v2 surfaces (Accuracy Lab, governance, the LLM Router) and selects the default adapter family; Aryx-o is Enterprise with the Oracle substrate.

   The **Graph read vertical** (the ask / graph / observability APIs) already routes through the container, so swapping a substrate (e.g. Oracle ADB later) is an adapter swap, not a rewrite. `src/aryx/naming.py` holds the driver-free `ws_graph(workspace_id)` helper — the seam imports it without pulling in `psycopg` or `falkordb`.

## Ask Engine

`src/aryx/ask/` produces grounded, cited answers rather than free-form LLM text:

- `evidence.py` — `RetrievedEntity`, the unit of retrieved evidence.
- `grounding.py` — `build_grounding(answer, entities)` verifies an answer against the retrieved evidence and emits `Citation`s drawn from source records.
- `ab.py` — `run_ab(...)` runs an ontology-on vs ontology-off comparison and scores the two variants (backs the Accuracy Lab `/lab/ab`).

`graph/retrieve.py` now exposes `gather()` (structured retrieval → `RetrievedEntity` list) alongside `render_context()` (the rendered LLM context).

## Data Explorer Read Model

`src/aryx/explore.py` is a pure aggregation layer over `EntityStore`'s relational source of truth — no graph dependency. It exposes `summarize()`, `entities_view()`, and `graph_view()`, which back the `/data/*` API and the web Data surface.

## Interactive Diagrams

- **[Business View](diagrams/business-view.html)** — User paths and backend flow
- **[Technical Flow](diagrams/technical-flow.html)** — 4-layer system architecture with all components

---

## Resolution Funnel

The ER pipeline is the core differentiator. Records flow through five stages:

```
  LANDED RECORDS
       │
  ┌────▼──────────────────────────────────────────────┐
  │ 1. BLOCK — MultiKeyBlocker                        │
  │    Prefix + token-set + Soundex keys               │
  │    Block-size cap prevents cartesian explosion      │
  │    Chunked mode: 3-pass streaming for large data    │
  └────┬──────────────────────────────────────────────┘
       │ candidate pairs
  ┌────▼──────────────────────────────────────────────┐
  │ 2. SCORE — cheap LLM (Ollama)                      │
  │    Pairwise similarity → float [0, 1]              │
  └────┬──────────────────────────────────────────────┘
       │ scored pairs
  ┌────▼──────────────────────────────────────────────┐
  │ 3. ROUTE — four-band adjudication                  │
  │    >=0.92  AUTO_MERGE (no human needed)             │
  │    0.90-0.92  ADJUDICATE (frontier LLM decides)    │
  │    0.75-0.90  REVIEW (queued for human steward)    │
  │    <0.75  REJECT                                    │
  │    Thresholds from measured sweep (DEC-003)         │
  └────┬──────────────────────────────────────────────┘
       │ merge decisions
  ┌────▼──────────────────────────────────────────────┐
  │ 4. CLUSTER — transitive closure                    │
  │    confidence = min merge-edge, clamp [0.5, 0.99]  │
  │    human edges → 0.99; singletons → 0.5            │
  └────┬──────────────────────────────────────────────┘
       │ entity clusters
  ┌────▼──────────────────────────────────────────────┐
  │ 5. GOLDEN RECORD — survivorship policy             │
  │    5 strategies: first_non_empty, source_priority,  │
  │    most_recent, most_complete, most_frequent        │
  │    Per-attribute overrides; conflict audit trail     │
  └───────────────────────────────────────────────────┘
```

**Key files:** `resolution/run.py`, `resolution/blocking.py`, `resolution/survivorship.py`, `resolution/golden.py`, `resolution/confidence.py`, `resolution/chunked.py`, `resolution/review_queue.py`

## Pipeline Stages (7-stage ingest)

| # | Stage | What | Cost |
|---|-------|------|------|
| 1 | **Extract** | Stream from DB connector or file reader | Free |
| 2 | **Land** | Store raw record + provenance in Postgres | PG write |
| 3 | **Tag** | Semantic field labels (email, phone, currency) | Ollama (free) |
| 4 | **Map** | Source → entity type; HITL approval gate | Frontier LLM |
| 5 | **Resolve** | Block → score → adjudicate → cluster → golden | Mix |
| 6 | **Relate** | FK links, co-occurrence, optional LLM inference | Deterministic + LLM |
| 7 | **Project** | Write entities + edges to FalkorDB graph | FalkorDB write |

Stage checkpoints (`StageTracker`) track running/done/failed per stage. Crashed pipelines resume from the last completed stage — leftover "running" on resume is treated as "failed".

**Chunked mode:** When record count exceeds `ARYX_ER_CHUNK_THRESHOLD` (default 100k), resolution switches to 3-pass streaming (key → score → cluster) via `ChunkBackend` protocol. Memory bound = largest block.

## Action Layer (Kinetic)

Declarative mutations defined as JSON with guard conditions (reusing the rules engine `_match`):

```
definition → validate → check_guard → apply_effects → audit log
```

- Effects: `set_attribute`, `get_attribute`, `find_entity`, `add_relationship`, `remove_relationship`
- All effects write Postgres-first with before/after snapshots
- MCP `act` tool is always-pending for agent-initiated mutations (human approves via API)
- Mirrors the adjudication queue shape: enqueue → page → decide

**Key files:** `actions/engine.py`, `store/action_store.py`, `api/actions_api.py`, `mcp/act.py`

## Incremental Projection

FalkorDB is never the source of truth — it is a projection of Postgres state.

- `project_auto()` checks the dirty-set size: <30% dirty → incremental, else full rebuild
- Dirty-set computation uses Postgres watermark + `aryx_projected_entity` side table
- Tombstones handle deleted entities (DETACH DELETE in FalkorDB)
- Full rebuild: wipe named graph, re-project all entities + relationships

**Key files:** `project.py`, `store/projection_store.py`, `graph/falkor_store.py`

## API Layer

The real app is `api/main.py:create_app()`, which registers **27 routers**. (A legacy `create_app()` / module-level `app` at the bottom of `graph_api.py` is dead code — it is not the app that runs.)

| Router | Prefix | Purpose |
|--------|--------|---------|
| graph | /graph | FalkorDB queries, paths (routes via ports container) |
| admin (entities) | /admin | Entity CRUD |
| ask | /ask | NL question answering (grounded, cited) |
| **lab** | /lab | **Accuracy Lab — `/lab/ab`, `/lab/reasoner`** |
| **data** | /data | **Data Explorer — `/data/summary`, `/data/entities`, `/data/graph`, `/data/relate`** |
| ask_history | /ask/history | Chat history |
| jobs | /jobs | Job status, resume |
| file_ingest | /ingest/files | Document upload + discovery |
| connect | /connect | Database introspection |
| demo_ingest | /demo | Synthetic support data |
| doc_discover | /discover | Document entity discovery |
| workspace | /workspaces | CRUD + survivorship policy |
| brief | /brief | Workspace brief |
| datasource | /datasources | Datasource registration + secrets |
| ingest_question | /ingest/questions | Onboarding ingest Q&A |
| relationship_type | /relationship-types | Relationship type catalog |
| ontology_assist | /ontology/assist | Ontology assistance |
| observability | /observability | Job metrics, LLM usage (routes via ports container) |
| ontology | /ontology | Type management, import/export |
| axioms | /axioms | OWL axiom management |
| shapes | /shapes | Shape constraints |
| rules | /rules | Business rules engine |
| rest_ingest | /ingest | Trigger ingest jobs |
| versions | /versions | Schema versioning |
| mcp_tokens | /mcp | MCP token management |
| adjudication | /adjudication | Human review queue |
| actions | /actions | Kinetic action CRUD + execute |

`security` remains a middleware, not a router.

**Auth:** `ApiKeyMiddleware` with three modes (off/optional/required). `_bearer_ok` returns False on any exception (fail-closed, DEC-006).

## MCP Integration

**21 tools** exposed over SSE (`mcp/server.py`, with tool definitions split across `mcp/tools*.py` — core, ingest, datasource, ontology, onboard). Core tools include:

| Tool | Purpose |
|------|---------|
| `list` | Browse entities and relationships |
| `ask` | Natural-language graph queries |
| `act` | Request mutations (always-pending, human-approved) |

The remaining tools cover datasource management, ingest Q&A, ontology, and the onboarding wizard.

## Storage

### Postgres (source of truth)

27 idempotent migrations (0001-0027), auto-applied on API startup.

Key tables:
- `aryx_entity` — canonical entities with confidence score
- `aryx_relationship` — typed edges with properties
- `aryx_landed_record` — raw records with source provenance
- `aryx_entity_member` — record-to-entity resolution mapping
- `aryx_ontology` — type catalog (proposed/approved status)
- `aryx_attribute_conflict` — survivorship conflict audit trail
- `aryx_adjudication` — human review queue with labeled-data semantics
- `aryx_run_stage` — pipeline stage checkpoints
- `aryx_projection_state` — watermark for incremental projection
- `aryx_action` / `aryx_action_execution` — kinetic action definitions and audit log
- `aryx_block_member`, `aryx_block_done`, `aryx_match_edge` — chunked resolution state

All entity tables LIST-partitioned by workspace_id for isolation and physical purge.

### FalkorDB (graph projection)

- Named graph per workspace (`aryx_ws_<id>`, derived via `naming.ws_graph()`)
- Nodes = entities, edges = relationships
- Wipe-and-rebuild safe; Postgres has the real data

### Connection Pooling

`psycopg3` shared pool singleton per DSN (`store/pool.py`). All 10 stores borrow from the pool instead of opening individual connections.

## Technology Stack

| Layer | Tech | Why |
|---|---|---|
| Language | Python 3.13 | Type hints; SQL in .sql files (DB-Guard enforced) |
| API | FastAPI | Async; auto-OpenAPI; Pydantic validation |
| UI (primary) | Next.js 15 | Isolated deploy unit; HTTP-only to API via `/api` proxy |
| UI (legacy) | Streamlit | Original UI; still present and runnable |
| Substrate seam | Ports & adapters | `module:Class` adapters per port; substrate-swappable (Lite/Enterprise/Aryx-o) |
| Database | PostgreSQL 16 | ACID, FTS, partitioning, JSONB |
| Graph | FalkorDB | Fast traversal; wipe/rebuild safe |
| Local LLM | Ollama | Private data; offline; zero-cost inference |
| Cloud LLM | Anthropic, OpenAI, Gemini | Frontier tier for hard decisions |
| Deploy | Docker Compose | Reproducible; local + EC2 |
| Pool | psycopg3 + psycopg_pool | Connection reuse across stores |

## Architectural Decisions

| ID | Decision | Rationale | Date |
|---|---|---|---|
| DEC-001 | Postgres source of truth; FalkorDB rebuildable | No graph-only state; safe to wipe | 2026-05-28 |
| DEC-002 | Streaming one-record-at-a-time | Same code path for small tables and TB datasets | 2026-05-28 |
| DEC-003 | Four-band thresholds from measured sweep | 0.92/0.90/0.75 from Febrl benchmark, not opinion | 2026-06-11 |
| DEC-004 | Survivorship policies over first-non-empty | Order-independent merge; auditable conflicts | 2026-06-11 |
| DEC-005 | Review-band pairs are non-merge (conservative) | False positive worse than false negative for ER | 2026-06-11 |
| DEC-006 | Auth fail-closed; _bearer_ok returns False on exception | Security over availability for auth path | 2026-06-11 |
| DEC-007 | Next.js web app is HTTP-only, isolated deploy unit | UI scales/deploys independently; no Python coupling | 2026-06-14 |
| DEC-008 | Ports & adapters seam over direct substrate calls | Oracle ADB later = adapter swap, not rewrite | 2026-06-14 |

## Next Steps

- [Install Guide](INSTALL.md) — Get running locally
- [User Guide](USER_GUIDE.md) — Navigate the UI
- [Feature Matrix](FEATURES.md) — All capabilities at a glance
