## Version: 1.1
## Last Updated: 2026-05-28
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
  `chunked.resolve_chunked` is a memory-bounded, crash-resumable variant for
  runs over `ARYX_ER_CHUNK_THRESHOLD` records (block-wise passes over a
  persistent `ChunkBackend`, sharing `run._route_decision` for band routing);
  not yet wired into `orchestrate.run_pipeline` — built and tested standalone.
- **Relationships** (`relationships.py`) — infers entity→entity edges from foreign
  keys and co-occurrence (deterministic) plus LLM for implied links.
- **Graph projection** (`graph/falkor_store.py`) — wipe-and-rebuild projection of
  ontology/entities/relationships into FalkorDB with provenance threads.
- **Queries** (`queries/`) — SQL-file loader keeping SQL out of Python (DB-Guard).
- **Config / logging** (`config.py`, `logging_setup.py`) — 12-factor settings from
  `ARYX_`-prefixed env vars; credentials never logged.

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
- Frontend: none (batch/worker service)
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
