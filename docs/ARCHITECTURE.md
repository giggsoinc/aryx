# Architecture

## System Overview

Aryx is a knowledge graph platform that ingests records from heterogeneous sources (databases, files), resolves duplicates into single entities, infers relationships, and builds a queryable graph.

**Core principle:** Postgres is the source of truth; FalkorDB is a rebuildable projection. Cheap, deterministic stages (blocking, scoring) shrink the search space so frontier LLMs only touch the hard ~1-5% of decisions.

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

23 routers registered in `api/main.py`:

| Router | Prefix | Purpose |
|--------|--------|---------|
| workspace | /workspaces | CRUD + survivorship policy |
| connect | /connect | Database introspection |
| rest_ingest | /ingest | Trigger ingest jobs |
| file_ingest | /ingest/files | Document upload + discovery |
| doc_discover | /discover | Document entity discovery |
| jobs | /jobs | Job status, resume |
| entities (admin) | /admin | Entity CRUD |
| graph | /graph | FalkorDB queries, paths |
| ask | /ask | NL question answering |
| ask_history | /ask/history | Chat history |
| ontology | /ontology | Type management, import/export |
| ontology_browse | /ontology/browse | OWL-style browse |
| rules | /rules | Business rules engine |
| axioms | /axioms | OWL axiom management |
| observability | /observability | Job metrics, LLM usage |
| versions | /versions | Schema versioning |
| mcp_tokens | /mcp | MCP token management |
| adjudication | /adjudication | Human review queue |
| actions | /actions | Kinetic action CRUD + execute |
| demo_ingest | /demo | Synthetic support data |
| security | — | Auth middleware |

**Auth:** `ApiKeyMiddleware` with three modes (off/optional/required). `_bearer_ok` returns False on any exception (fail-closed, DEC-006).

## MCP Integration

3 tools exposed over SSE (`mcp/server.py`):

| Tool | Purpose |
|------|---------|
| `list` | Browse entities and relationships |
| `ask` | Natural-language graph queries |
| `act` | Request mutations (always-pending, human-approved) |

## Storage

### Postgres (source of truth)

23 idempotent migrations (0001-0023), auto-applied on API startup.

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

- Named graph per workspace (`ws_1`, `ws_2`, etc.)
- Nodes = entities, edges = relationships
- Wipe-and-rebuild safe; Postgres has the real data

### Connection Pooling

`psycopg3` shared pool singleton per DSN (`store/pool.py`). All 10 stores borrow from the pool instead of opening individual connections.

## Technology Stack

| Layer | Tech | Why |
|---|---|---|
| Language | Python 3.13 | Type hints; SQL in .sql files (DB-Guard enforced) |
| API | FastAPI | Async; auto-OpenAPI; Pydantic validation |
| UI | Streamlit | Rapid iteration; live updates without JS |
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

## Next Steps

- [Install Guide](INSTALL.md) — Get running locally
- [User Guide](USER_GUIDE.md) — Navigate the UI
- [Feature Matrix](FEATURES.md) — All capabilities at a glance
