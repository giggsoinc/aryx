# Feature Matrix

Comprehensive list of Aryx capabilities as of the V2 release (June 2026).

## Editions

| Edition | Version | Notes | Component |
|---------|---------|-------|-----------|
| Lite | v1 | Core ingest → resolve → graph → Ask | `edition.py`, `ARYX_EDITION` |
| Enterprise | v2 | Web UI, Accuracy Lab, Data Explorer, ports & adapters | `edition.py`, `ARYX_EDITION` |
| Aryx-o | v2.1 | Oracle-native adapter set | `edition.py`, `ARYX_EDITION` |

See [EDITIONS.md](EDITIONS.md) for the full edition matrix.

## Ingest & Discovery

| Feature | Status | Component |
|---------|--------|-----------|
| Postgres connector (streaming) | Done | `connectors/postgres.py` |
| MySQL / MariaDB / Oracle connector | Done | `connectors/sql_source.py` |
| REST API connector | Done | `connectors/rest_api.py` |
| File upload (CSV, JSON, PDF, DOCX, PPTX, images) | Done | `connectors/{csv_source,json_source,pdf,docx,pptx,image}.py` |
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
| Interactive graph explorer (web) | Done | `apps/web` Data / Model surfaces |
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

## Web UI (V2)

Next.js application (`apps/web/`, isolated from the Python service).

| Feature | Status | Component |
|---------|--------|-----------|
| Ask surface (grounded NL Q&A) | Done | `apps/web/app/page.tsx` (`/`) |
| Model surface (ontology view/edit) | Done | `apps/web/app/model/` (`/model`) |
| Data surface (Data Explorer) | Done | `apps/web/app/data/` (`/data`) |
| Lab surface (Accuracy Lab) | Done | `apps/web/app/lab/` (`/lab`) |
| Onboard wizard | Done | `apps/web/app/start/` (`/start`) |
| Settings — LLM provider / keys | Done | `apps/web/app/settings` |

## Accuracy Lab (V2)

Trust and evaluation surface at `/lab` (`api/lab_api.py`, `aryx.ask`).

| Feature | Status | Component |
|---------|--------|-----------|
| Groundedness engine (claim → citations traced to source records) | Done | `ask/grounding.py` |
| Hallucination signal (ungrounded-claim detection) | Done | `ask/grounding.py` |
| Ontology on/off A/B (same model, ON vs OFF, scorecard) | Done | `ask/ab.py` |
| Read-only reasoner-check (axiom contradictions, dry-run) | Done | `api/lab_api.py` |

## Data Explorer (V2)

Multi-lens data browser at `/data` (`api/data_api.py`, `aryx.explore`).

| Feature | Status | Component |
|---------|--------|-----------|
| Tree lens (types → entities → attributes + provenance) | Done | `explore.py` |
| Table lens (records grid + provenance drawer) | Done | `explore.py` |
| Graph lens (type-level map — nodes per type sized by count, edges aggregated by relationship) | Done | `explore.py` |
| FK-relate (derive relationships from foreign-key attribute links) | Done | `api/data_api.py` (`/data/relate`) |

## Ports & Adapters (V2)

Capability seam (`aryx.ports`) — the Oracle-readiness foundation. Adapter selection is config-driven via `ARYX_ADAPTER_*`.

| Capability Port | Default Adapter | Component |
|-----------------|-----------------|-----------|
| Relational | Postgres | `ports/protocols.py`, `ports/container.py` |
| Graph (read) | FalkorDB | `ports/protocols.py` |
| Graph (write) | FalkorDB | `ports/protocols.py` |
| Vector | Postgres | `ports/protocols.py` |
| LLM | Ollama | `ports/protocols.py` |
| Reasoner | (built-in) | `ports/protocols.py` |
| Compute | (built-in) | `ports/protocols.py` |

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
| 27 idempotent migrations (auto-apply) | Done | `store/migrations/` |
| Ports & adapters seam (config-driven) | Done (V2) | `ports/` |
| Editions (Lite / Enterprise / Aryx-o) | Done (V2) | `edition.py` |
| Docker Compose deployment | Done | `docker-compose.yml` |
| Git-only update flow (EC2) | Done | [INSTALL.md](INSTALL.md) |
| Provider-agnostic LLM broker | Done | `llm/broker.py` |
| Token budget + rate limiting | Done | `llm/governor.py` |
| Job observability (status, tokens, latency) | Done | `api/observability_api.py` |
| Demo data loader (synthetic support tickets) | Done | `demo/loader.py` |

## MCP Integration

21 tools over SSE (`mcp/server.py`, `mcp/sse.py`). Grouped below.

| Tool group | Tools | Component |
|------------|-------|-----------|
| Workspace | `workspace_create`, `workspace_list`, `workspace_select` | `mcp/server.py` |
| Brief | `brief_set`, `brief_get`, `brief_draft`, `brief_save` | `mcp/onboard.py`, `mcp/tools_onboard.py` |
| Datasource | `datasource_add`, `datasource_list`, `datasource_test`, `datasource_quiz`, `datasource_delete` | `mcp/datasource.py`, `mcp/tools_datasource.py` |
| Ingest | `ingest_questions`, `ingest_answer`, `ingest_status` | `mcp/ingest_hitl.py`, `mcp/tools_ingest.py` |
| Ontology | `ontology_get`, `ontology_export` | `mcp/ontology.py`, `mcp/tools_ontology.py` |
| Entities | `entities_preview` | `mcp/tools.py` |
| Core | `ask`, `act`, `list` | `mcp/tools.py`, `mcp/act.py` |
| SSE transport | — | `mcp/sse.py` |

## Quality & Testing

| Metric | Value | Source |
|--------|-------|--------|
| Test count | 121 | `tests/test_*.py` (14 files) |
| Febrl1 Precision | 1.00 | `make er-bench-quick` |
| Febrl1 Recall | 0.59 | `make er-bench-quick` |
| Febrl1 F1 | 0.74 | `make er-bench-quick` |
| Blocking recall | 0.852 | `make er-bench` |
| Python source files | 174 | `src/aryx/` |
| SQL migrations | 27 | `store/migrations/` |
| API routers | 27 | `api/main.py` |
| MCP tools | 21 | `mcp/server.py` |
