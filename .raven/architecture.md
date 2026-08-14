## Version: 1.5.2
## Last Updated: 2026-08-11
## Project: Aryx

### System Overview
Aryx ingests records from many heterogeneous sources, lands them in a relational
store with full provenance, semantically tags their fields, then reasons over
them to build a knowledge graph: it maps source schemas to a canonical ontology,
resolves duplicate records across systems into single entities, infers
relationships, and projects the result into FalkorDB. The relational database is
the permanent source of truth; the graph is a rebuildable projection. Expensive
frontier-LLM reasoning is rationed by a funnel of cheap, deterministic and local
stages so the model only touches the hard ~1–5% of decisions.

On top of that ingested/graphed data sits a second pipeline (C07-C15) that turns
an approved dataset + knowledge graph into a governed, rendered dashboard: an
LLM drafts a candidate spec from an explicit approved-resources allow-list only,
every reference in that draft is re-verified deterministically in code (never
trusted at face value), and only what survives validation is compiled, executed,
and composed into what the frontend renders. Same funnel discipline as the
ingestion side — the LLM proposes, code disposes.

### Components
- **Connectors** (`connectors/`) — pluggable source readers behind a `Connector`
  protocol; `postgres.py` is the first concrete reader. Stream rows via `extract()`.
- **Pipeline spine** (`pipeline/`) — `run.run_spine` streams extract → `clean` →
  `profile` one record at a time (never materializes the full dataset); `tag.py`
  applies semantic field tags via the cheap model tier.
- **Store** (`store/`) — the RDB source of truth: `migrate` applies numbered SQL
  migrations, `postgres_store`/`entity_store`/`ontology_store` persist landed
  records, resolved entities and ontology, `batch_sink` is the landing sink.
- **Broker** (`broker/`) — provider-agnostic model gateway. `registry` holds
  `ModelSpec`s queryable by `Tier` (local/cheap/frontier); `governor` enforces
  budget/routing; `discovery` finds available models; `secrets` resolves
  credentials; supports Anthropic, Ollama and OpenAI-compatible providers, plus
  local `embed()` for blocking (Anthropic has no embeddings API).
- **Ontology mapping** (`ontology/`) — `mapping.py` is the frontier-tier agent
  that maps source table→canonical type and field→attribute and proposes new
  types; `sources.py` plugs seed vocabularies (schema.org / DD / MDM / RDF).
- **Resolution funnel** (`resolution/`) — `classical.block`+`score_pair` (cheap),
  `adjudicate` (frontier, ambiguous middle only), `cluster` (UnionFind transitive
  closure + golden record); `run.resolve` wires them into entities + members.
- **Relationships** (`relationships.py`) — infers entity→entity edges from foreign
  keys and co-occurrence (deterministic) plus LLM for implied links.
- **Derive entities** (`pipeline/derive_entities.py`, `api/pipeline_derive_api.py`)
  — from the Model tab, deduplicates an already-resolved type's column into a
  real, populated new entity type (e.g. every ContractLineItem row sharing a
  Customer Number becomes one Customer entity); provenance carries forward as
  the union of landed_record_ids behind each folded group.
- **Explicit entity linking** (`api/pipeline_link_api.py`, wraps
  `pipeline/orchestrate.link_entities`) — from the Model tab, draws a real,
  data-level FK edge (exact-value match) between two already-ingested types;
  distinct from `POST /ontology/relationships`, which only labels a cosmetic
  diagram edge with no effect on the graph.
- **Graph projection** (`graph/falkor_store.py`) — wipe-and-rebuild projection of
  ontology/entities/relationships into FalkorDB with provenance threads.
- **Queries** (`queries/`) — SQL-file loader keeping SQL out of Python (DB-Guard).
- **LLM dispatch** (`llm.py`, `llm_providers.py`) — `complete_json`/`complete_text`
  is the one dispatcher every backend LLM caller (planner, ontology mapping,
  resolution, tagging) routes through; per-provider-family tuning (e.g.
  `reasoning_effort` for hidden-reasoning models, `temperature`) lives here, not
  per-caller. Every call is logged to `aryx_llm_call`, tagged by `source` (`ask`
  for the interactive path vs. `pipeline` for everything else) — this is
  write-only today; the frontend "Usage" tab and its backend query endpoint
  (`api/observability_api.py`) were both removed, so nothing currently reads
  this table back.
- **Config / logging** (`config.py`, `logging_setup.py`) — 12-factor settings from
  `ARYX_`-prefixed env vars; credentials never logged.
- **Ports** (`ports/`) — six capability-port `Protocol` contracts (structural,
  duck-typed) so a future Oracle/Fabric/Vertex adapter can swap in via config
  without call-sites changing. Phase 0 wires `GraphReaderPort`/`GraphStorePort`
  end-to-end (used by C12's `graph_relation` execution); the other four are
  defined as a forward contract, migrated incrementally.
- **Kinetic actions** (`actions/`, G13) — declared, audited graph mutations
  (`set_attribute`/`add_relationship`/`remove_relationship`/`set_label`; no
  entity deletes, no source-system writeback yet). Guard → effects → audit
  log; effects apply to Postgres first (source of truth), never the graph
  directly — the projector's dirty-set picks up the change. Reuses the same
  when-clause matcher as `reasoning/engine.py` — one condition grammar across
  rules, axioms, and actions.
- **MCP server** (`mcp/`) — stdio + SSE server wrapping the REST API so any
  MCP host can drive Aryx; tool specs for datasource/ingest/onboard/ontology
  actions live in `mcp/tools_*.py`. Mounted at `/mcp` in the FastAPI app with
  bearer-token auth (`_bearer_ok` in `api/mcp_mount.py`); allow-all only when no
  tokens have been issued yet.

#### Dashboard planning pipeline (C01-C15)
- **C01 User Intent Capture** (`intent/`) — deterministic front-door for a
  dashboard request: collects domain, plain-language objective, and optional
  preferences into a versioned `user_intent` with a correlation id. No LLM;
  required fields block, unsupported catalogue values become warnings, never
  invented substitutes.
- **C03 Dataset Profiler** (`profiler/`) — reads an immutable dataset
  snapshot (C02) and measures file/table/column structure, quality, types,
  distributions, and analytical roles (`candidate_role`: identifier/measure/
  dimension/time/status/attribute) into a versioned `dataset_profile` — the
  authoritative source of real column names/types/cardinality for everything
  downstream, including C07's `ApprovedColumn` and C08's chart-fitness
  grounding. No LLM.
- **C05 Knowledge Graph Intake & Validation** (`graph_intake/`) — accepts a
  knowledge-graph JSON (derived from the workspace's entities/relationships),
  validates and normalizes it deterministically without changing business
  meaning, hashes it, and stores the original immutably with a validated
  version. No LLM.
- **C06 Knowledge Graph Profiler** (`graph_profiler/`) — summarizes the
  validated C05 graph into deterministic statistics + a compact schema, and
  exposes only VERIFIED, bounded paths backed by real relationship instances
  — a model may explain a verified path but never invent a node/relationship/
  path, and no path exceeds the requested depth bound.
- **C07 Context/Resource Retrieval** (`planning/`) — assembles one versioned
  `PlanningContext` from the dataset profile, semantic profile, graph profile,
  and the approved operation/chart catalogues; applies a role filter + budget
  cap so only analytically useful, size-bounded resources reach the planner.
  Also carries `graph_path_hints` (readable label/depth per verified graph
  path) and `graph_quality_notes` (C06 quality flags/limitations as plain
  strings) — added so the planner isn't citing bare graph-path ids blind.
- **C08 Andie Planner** (`andie_planner/`) — `prompt.py` builds a prompt from
  ONLY the approved resources in the C07 context; the LLM drafts a candidate
  `DashboardSpec` (business questions, KPIs, analyses, visualizations);
  `ground.py` re-validates every column/operation/chart-type/cross-reference
  deterministically against the same approved resources — anything unsupported
  is dropped and recorded as a warning, never invented or substituted. Includes
  the `graph_relation` operation (a chart sourced from a live knowledge-graph
  relationship — e.g. "contracts per account manager" — instead of a flat
  dataset column) and `delta.py`, a narrower "ask for one chart in natural
  language" extension that merges into an existing approved spec.
  `filter_repair.py` is a targeted post-grounding micro-repair: when a KPI's
  filter is left without a value, one narrow follow-up call offers only that
  column's real `sample_values` and either fills it or the whole KPI is
  dropped — never a full-spec redraft, and never an unfiltered operand
  passed off as a real result. `schema.py`'s `operation`/`chart_type`/
  `zero_denominator_policy`/ratio-operand fields carry real JSON-schema
  `enum`s pinned to the same catalogues C09 enforces (`tests/test_schema.py`)
  — additive hallucination guardrails, not yet enforced by every provider's
  completion call (see Architecture Decisions).
- **C09 Spec Validation** (`spec_validation/`) — ten deterministic checks
  (schema, column existence, formula validity, chart/axis compatibility,
  lineage, claim safety, and others) run against the grounded spec; a
  rejection triggers exactly one bounded LLM repair retry, never more.
- **C10 Preprocessing** (`preprocess/`) — converts an approved dataset's raw
  rows into the typed shape the execution compiler's templates expect.
- **C11 Execution Compiler** (`execution_compiler/`) — binds each approved
  KPI/analysis to one of a fixed set of vetted execution templates
  (`templates.py`); an operation with no template has no execution path. Pure
  and I/O-free, with one deliberate exception: a `graph_relation` analysis
  compiles to a `graph_relation_count` node carrying only an opaque
  `path_id` — the real graph query triple is resolved later, at execution
  time, since the compiler has no DB/graph access (see Architecture Decisions).
- **C12 Analysis Execution** (`analysis_execution/`) — runs the compiled plan
  node-by-node against real typed rows; a `graph_relation_count` node instead
  queries FalkorDB through an injected `GraphReaderPort`, after
  `resolve_graph_relation_nodes` looks up the workspace's graph profile and
  resolves the path id to a concrete `(source_type, relationship,
  target_type)` triple. An unresolvable or unsupported (multi-hop) path fails
  only that one node — same controlled-degradation contract as an unknown
  template or a missing column, never a crash or a silently invented result.
- **C13 Post-Execution Validation** (`post_execution_validation/`) —
  independently recomputes every KPI and analysis result from scratch
  (`recompute.py`, reusing C12's own node-execution primitives, including the
  graph query path) and cross-checks it against what was reported — a
  structurally valid but numerically tampered or incorrect result is still
  caught and rejected.
- **C14 Dashboard Composition** (`dashboard_composition/`) — arranges an
  approved spec's validated results into an ordered dashboard model
  (sections, components, layout); never computes or alters a value itself.
- **C15 Frontend Renderer** (`apps/web/`) — Next.js app; renders the composed
  dashboard model with Plotly-based charts (`PlotlyChart.tsx`/`plotlySpecs.ts`)
  covering bar/line/scatter/sankey/treemap/gantt/survival curves and more.
  The only piece of C15 that touches the backend is telemetry
  (`dashboard_render/models.py` + `api/render_telemetry_api.py`) — the
  frontend reports render/interaction stats after each render; no recompute
  of a governed KPI formula ever happens client-side.

### Data Flow
```
Sources (Postgres, + Drive/Salesforce/Odoo planned)
  → Connector.extract()
  → clean → profile          (stages 1–3, streaming spine)
  → land in RDB w/ provenance (stage 2 sink)
  → tag fields               (stage 4, cheap tier)
  → ontology mapping agent   (stage 5a, frontier + HITL gate)
  → resolution funnel        (stage 5b: normalize→block→score→adjudicate→cluster)
  → relationship inference   (stage 5c)
  → FalkorDB projection       (stage 5d, rebuildable from RDB)

Dashboard planning, on top of the above — auto-chained end to end
(`aryx.pipeline.auto_chain.run_auto_chain`, triggered by
`aryx.pipeline.chain_jobs` off a Brief save / valid intent capture / file
ingest) and stopping only on a genuine blocker: C09 rejects the spec twice,
C13 marks the execution results ineligible, or C14 drops every
visualization. A manual "Generate/Run/Compose" button per stage still
exists as an escape hatch for per-dataset iteration and forcing a fresh run:
  → C07 context assembly       (dataset + semantic + graph profile -> approved resources)
  → C08 Andie Planner          (LLM drafts DashboardSpec -> ground.py re-verifies, never trusts)
  → C09 spec validation        (10 checks, one bounded repair retry) — BLOCKS the chain on rejection
  → C10 preprocessing          (typed rows for the approved dataset)
  → C11 execution compiler     (KPI/analysis -> vetted template nodes)
  → C12 analysis execution     (run nodes against rows, or FalkorDB for graph_relation)
  → C13 post-execution validation (independent recompute + cross-check) — BLOCKS if ineligible
  → C14 dashboard composition  (arrange into an ordered dashboard model) — BLOCKS only if every
                                visualization was dropped; partial dashboards proceed
  → C15 frontend renderer      (Next.js + Plotly)
```

### Deployment Topology
- Cloud: AWS (secrets via `boto3` / Secrets Manager / SSM)
- Compute: containerized 12-factor `worker`; production orchestrator (ECS/EKS/OCI)
  decided at rollout — not yet fixed
- Database: PostgreSQL 16 (source of truth)
- Graph: FalkorDB (rebuildable projection)
- Local dev: `docker-compose` — `postgres` (host port 55432), `falkordb` (6379),
  `worker` (built from `Dockerfile`); worker waits on a healthy Postgres

### Tech Stack
- Language: Python 3.13 (SQL in `.sql` files; YAML for infra)
- Backend service: batch/worker (ingestion side) + FastAPI (`aryx.api`, serves
  the dashboard-planning pipeline's endpoints)
- Frontend: Next.js (`apps/web/`) — Plotly-based dashboard rendering (C15)
- Data / models: pydantic 2.x, pydantic-settings, psycopg 3 (binary), anthropic,
  falkordb; local embeddings via Ollama
- Infra: Docker, Docker Compose; AWS (boto3)

### Architecture Decisions
| Decision | Rationale | Date |
|---|---|---|
| RDB is source of truth; FalkorDB is a rebuildable projection | Graph can be wiped and rebuilt from Postgres anytime; no graph-only state to lose | 2026-05-28 |
| Streaming, one-record-at-a-time spine (no full-dataset load) | Same code path serves a small table or a terabyte — slower, not crashing | 2026-05-28 |
| Resolution funnel; frontier LLM only on the ambiguous ~1–5% | Cheap/local/deterministic layers shrink n² so frontier dollars are rationed | 2026-05-28 |
| Provider-agnostic Broker with tiered routing | Decouple from any single vendor (Anthropic/Ollama/OpenAI-compatible) | 2026-05-28 |
| Local Ollama embeddings for blocking | Anthropic has no embeddings API; keeps private data on-box, avoids egress | 2026-05-28 |
| HITL gate for new ontology types + low-confidence merges | Nothing untraceable lands; human decisions become future ER training labels | 2026-05-28 |
| SQL kept out of Python via `queries/*.sql` loader | DB-Guard discipline; reviewable, lint-able SQL | 2026-05-28 |
| OpenAI endpoints blocked in manifest | Prevent private-data egress to non-approved providers | 2026-05-28 |
| graph_relation charts resolve their graph triple at execution time, not planning time | C07/C08 only carry a `path_id` allow-list (governed vocabulary, same shape as `supported_operations`/`supported_charts`); the full verified-path type/relationship info isn't available until `GraphProfileStore` is queried, which requires DB access the execution compiler (C11) deliberately doesn't have | 2026-08-05 |
| `schema.py`'s new `enum` fields are additive, not yet provider-enforced | `llm_providers.openai_json` (Groq/Gemini) sends `response_format: json_object`, not `json_schema`, so these enums aren't transmitted as a hard constraint yet — `ground.py`/`checks.py` remain the real enforcement until a separate, live-tested switch to `json_schema` mode ships | 2026-08-07 |
