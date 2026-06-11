# Aryx Gap Map — Immutable Ground Truth
# DO NOT EDIT — agents derive baselines from this file

## G4 — Fail-Open Auth
- `src/aryx/api/main.py:43` — `_bearer_ok` returns `True` when token-store listing raises
- `src/aryx/api/main.py:49` — outer exception handler also returns `True`
- `ARYX_MCP_AUTH_OPTIONAL` defaults to `"1"` (allow-all when no token presented)
- 18 REST routers in `main.py` have **no auth of any kind**

## G2 — Naive Blocking
- `src/aryx/resolution/classical.py:block_key` — blocks only on `text[:4]` (first 4 chars normalized)
- Consequence: "Smith, John" and "Smithson, Alice" land in the same block; "John Smith" and "Smith John" land in different blocks
- Cross-type records never compared: blocking happens per `ontology_type` batch only
- No phonetic / token-set fallback; purely lexical prefix

## G9 — No ER Benchmark
- No `make er-bench` target exists
- No benchmark dataset in `tests/fixtures/`
- Precision/recall never measured; regressions undetectable
- Depends on G2 (improved blocking changes recall baseline)

## G3 — Incomplete Golden Record
- `src/aryx/resolution/cluster.py:golden_record` — first-non-empty-value merge only
- No attribute-level confidence weighting (newer source vs older source indistinguishable)
- No conflict detection: contradictory values (two different emails) → first wins silently
- No provenance per merged attribute (can't trace which source contributed which field)

## G10 — No HITL Adjudication Queue
- `src/aryx/resolution/adjudicate.py` — single frontier LLM call, no queue, no audit trail
- Ambiguous band (0.90–0.92) decisions are unreviewed and unlogged in a queryable way
- No escalation ladder: Claude API + ChatGPT parallel → human fallback
- No HITL UI surface in Streamlit
- No MCP tools for AI-as-reviewer pattern
- Depends on G2 (blocking surfaces the pairs), G9 (benchmark validates the queue reduces errors)

## G1+G5 — Pipeline Scale + Resume
- No per-stage checkpointing; full re-run on any failure
- `JobStore` tracks status but pipeline does not read it for resume
- No back-pressure / concurrency cap on parallel ingest jobs
- Embedding stage can OOM on large datasets (no chunking strategy)
- Depends on G2 (blocking must complete before scale matters)

## G12 — Missing Connection Pooling
- `src/aryx/store/*.py` — each store opens `psycopg.connect()` directly
- No PgBouncer or `psycopg_pool` usage
- Under concurrent API load: connection count = requests × stores (≥10 per request)
- Postgres default `max_connections=100` exhausted by ~10 concurrent users
- Independent of all other gaps

## G7 — Confidence Scores Are Wrong
- `src/aryx/resolution/run.py` — `confidence=1.0` for any multi-member cluster, `0.5` for singletons
- Score ignores: pair similarity at merge time, LLM adjudicator certainty, cluster size >2
- Downstream: graph query results ranked by confidence are meaningless
- Depends on G2 (blocking affects which pairs are compared)

## G8 — No Incremental Projection
- `src/aryx/project.py` — full graph re-project on every run: DROP + recreate all nodes
- FalkorDB `ws_<id>` graph wiped and rebuilt each time; history lost
- Unusable for append-only ingest patterns on large workspaces
- Depends on G1+G5 (scale work reveals this bottleneck)

## G13 — No Kinetic / Action Layer
- Rules engine (`reasoning/engine.py`) evaluates conditions but has no output channel
- `set_label` and `add_relationship` only write to the graph — no external actions
- No webhook, no event emission, no CRM write-back
- No action DSL grammar (G10 adjudication patterns should reuse the `when` matcher)
- Depends on G10 (action-architect reuses the decide-endpoint pattern)
