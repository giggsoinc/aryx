# Feature Matrix

Comprehensive list of Aryx capabilities as of the gap-closure program completion (June 2026).

## Ingest & Discovery

| Feature | Status | Component |
|---------|--------|-----------|
| Postgres connector (streaming) | Done | `connectors/postgres.py` |
| MySQL connector | Done | `connectors/mysql.py` |
| Oracle connector | Done | `connectors/oracle.py` |
| File upload (CSV, JSON, PDF, DOCX, PPTX, images) | Done | `connectors/file.py` |
| AI auto-discovery (schema → entity types) | Done | `pipeline/orchestrate.py` |
| Context-driven discovery (user provides domain context) | Done | UI Ingest tab |
| Streaming one-record-at-a-time pipeline | Done | `pipeline/spine.py` |
| Semantic field tagging (Ollama) | Done | `pipeline/orchestrate.py` |

## Entity Resolution

| Feature | Status | Component |
|---------|--------|-----------|
| Multi-key blocking (prefix + token-set + Soundex) | Done (G2) | `resolution/blocking.py` |
| Block-size cap (prevents cartesian explosion) | Done (G2) | `resolution/blocking.py` |
| Pairwise scoring (cheap LLM) | Done | `resolution/run.py` |
| Four-band adjudication routing | Done (G3/G10) | `resolution/run.py` |
| LLM adjudication (frontier tier, 0.90-0.92 band) | Done | `resolution/run.py` |
| Human review queue (0.75-0.90 band) | Done (G10) | `resolution/review_queue.py`, `api/adjudication_api.py` |
| Labeled training data persistence | Done (G10) | `store/adjudication_store.py` |
| Survivorship policies (5 strategies) | Done (G3) | `resolution/survivorship.py` |
| Per-attribute strategy overrides | Done (G3) | `resolution/golden.py` |
| Conflict audit trail | Done (G3) | `store/entity_store.py`, migration 0019 |
| Cluster confidence (weakest merge-edge) | Done (G7) | `resolution/confidence.py` |
| Chunked 3-pass resolution (streaming) | Done (G1) | `resolution/chunked.py` |
| Stage checkpoints (crash recovery) | Done (G5) | `store/checkpoint_store.py` |
| Pipeline resume from checkpoint | Done (G5) | `pipeline/stages.py` |
| ER benchmarks (Febrl, make er-bench) | Done (G9) | `tests/er_bench/` |

## Knowledge Graph

| Feature | Status | Component |
|---------|--------|-----------|
| FalkorDB projection (named graph per workspace) | Done | `project.py`, `graph/falkor_store.py` |
| Full graph rebuild | Done | `project.py` |
| Incremental projection (dirty-set watermark) | Done (G8) | `store/projection_store.py` |
| Auto mode selection (full vs incremental) | Done (G8) | `project.py` |
| Entity tombstones (delete propagation) | Done (G8) | `graph/falkor_store.py` |
| Interactive graph explorer (Streamlit) | Done | `ui/graph_panel.py` |
| Entity drill-down (properties, neighbors, provenance) | Done | UI Graph tab |
| Shortest-path queries | Done | `graph/falkor_store.py` |

## Intelligence & Querying

| Feature | Status | Component |
|---------|--------|-----------|
| Natural-language Ask (chat) | Done | `api/ask_api.py` |
| Conversation context (multi-turn) | Done | `api/ask_history_api.py` |
| Source provenance in answers | Done | `api/ask_api.py` |
| Business rules engine | Done | `reasoning/engine.py` |
| OWL axiom management | Done | `api/axioms_api.py` |

## Actions (Kinetic Layer)

| Feature | Status | Component |
|---------|--------|-----------|
| JSON DSL action definitions | Done (G13) | `actions/engine.py` |
| Guard conditions (reuses rules engine) | Done (G13) | `actions/engine.py` |
| Effect types (set/get attr, find entity, add/remove rel) | Done (G13) | `store/action_store.py` |
| Before/after audit log | Done (G13) | `actions/engine.py` |
| Human approval gate | Done (G13) | `api/actions_api.py` |
| MCP `act` tool (always-pending for agents) | Done (G13) | `mcp/act.py` |
| Versioned action definitions (append-only) | Done (G13) | `store/action_store.py` |

## Ontology

| Feature | Status | Component |
|---------|--------|-----------|
| OWL/Turtle/JSON-LD/RDF import | Done | `api/ontology_api.py` |
| RDF/Turtle/JSON-LD export | Done | `api/ontology_api.py` |
| Proposed → approved HITL gate | Done | `ui/ontology_sections.py` |
| Schema diagram (auto-generated) | Done | `ui/ontology_diagram.py` |
| Type editor (add/modify types) | Done | `ui/ontology_editor.py` |

## Platform & Operations

| Feature | Status | Component |
|---------|--------|-----------|
| Workspace isolation (LIST-partitioned) | Done | `store/entity_store.py` |
| API-key auth (off/optional/required) | Done (G4) | `api/security.py` |
| Fail-closed auth (exception → reject) | Done (G4) | `api/security.py` |
| psycopg3 connection pooling | Done (G12) | `store/pool.py` |
| 23 idempotent migrations (auto-apply) | Done | `store/migrations/` |
| Docker Compose deployment | Done | `docker-compose.yml` |
| Git-only update flow (EC2) | Done | [INSTALL.md](INSTALL.md) |
| Provider-agnostic LLM broker | Done | `llm/broker.py` |
| Token budget + rate limiting | Done | `llm/governor.py` |
| Job observability (status, tokens, latency) | Done | `api/observability_api.py` |
| Demo data loader (synthetic support tickets) | Done | `demo/loader.py` |

## MCP Integration

| Feature | Status | Component |
|---------|--------|-----------|
| `list` tool (browse entities) | Done | `mcp/tools.py` |
| `ask` tool (NL graph queries) | Done | `mcp/tools.py` |
| `act` tool (request mutations) | Done (G13) | `mcp/act.py` |
| SSE transport | Done | `mcp/sse.py` |

## Quality & Testing

| Metric | Value | Source |
|--------|-------|--------|
| Test count | 121 | `tests/test_*.py` (14 files) |
| Febrl1 Precision | 1.00 | `make er-bench-quick` |
| Febrl1 Recall | 0.59 | `make er-bench-quick` |
| Febrl1 F1 | 0.74 | `make er-bench-quick` |
| Blocking recall | 0.852 | `make er-bench` |
| Python source files | 174 | `src/aryx/` |
| SQL migrations | 23 | `store/migrations/` |
| API routers | 23 | `api/main.py` |
| MCP tools | 3 | `mcp/tools.py` |
