# Aryx: Remove FalkorDB, Graph on Postgres (Option A plan)

As of 2026-11-07 · Branch: `feat/remove-falkordb-pg-graph` · Status: implemented and staged, not yet committed

**Source of record:** the Claude doc this was exported from (https://claude.ai/artifact/TAERL61VM16fS8B2zS7Rod, revision 58). This file mirrors it so the plan lives next to the code; keep the two in step.

## Summary

**Decision: remove FalkorDB and read the graph straight from the Postgres tables that already hold every entity, edge and source link (Option A). Estimate: about 11 developer days (11.25), plus about 2 days contingency.**

- **Why it works:** Postgres already holds all graph data (`aryx_entity`, `aryx_relationship`, `aryx_entity_member`, `aryx_landed_record`), partitioned by workspace. FalkorDB only holds a rebuilt copy (DEC-001). The web Data Explorer (`/data/*`) already reads Postgres and never touched FalkorDB.
- **What FalkorDB serves today:** the Ask flow, the `/graph/*` API (also used by the MCP tools), analysis execution (`count_by_relationship`), observability counts, and the reasoning engine.
- **What gets deleted:** the graph writer and reader, the projector, the `falkordb` dependency, container, volume and CI service, and the `graph_url` argument threaded through 6 function signatures and about 20 call sites, plus the unused projection tables and the updated\_at column (migration 0048).
- **What gets added:** a Postgres graph reader (7 queries, shortest path as a bounded breadth-first search), one additive migration (0047), and two small tables for rule-inferred edges and labels.
- **Behaviour changes users will see:** the graph is always current (no stale copy); `POST /graph/cypher` goes away; `/admin/system/status` loses its `falkordb` block; rule-inferred edges are rebuilt on demand instead of vanishing silently.
- **Estimate revised:** I first said 6–9 days. The full audit found more surface (14 direct `FalkorStore(...)` constructions, 7 test files stubbing the driver, 35+ docs), so about 11 is the honest number.

**How this was audited:** every `falkor`, `graph_url`, `ws_graph`, `redis://`, `6379`, `GraphReader`, graph port and `project_*` reference across `src`, `scripts`, `tests`, `apps/web`, `docs`, CI and compose. Raven's guard blocks reading `.env*` files, so the line `ARYX_GRAPH_URL=redis://falkordb:6379` in `.env.example` is known only from a grep hit; someone with access must edit it. Excluded from the search: Raven's own tooling folders, node\_modules and build output. Binary files cannot be searched; see the note under Docs.

## As built

All eight phases are implemented on `feat/remove-falkordb-pg-graph`, staged but not committed. Verified: 78 unit-test modules, 80 end-to-end tests (against a real Postgres, FalkorDB-free), the web typecheck, and the commit-time decision-map gate all pass. Departures from this plan:

- **Seven projection SQL files were deleted, not eight.** `select_relationships_for_entities.sql` is still used by `EntityStore.relationships_for_entities` (the adjudication API). My inventory called it projector-only; the end-to-end suite caught the mistake and the file is restored.
- **`OntologyStore.ancestors` stays.** Only the `_build_type_ancestors` helper that fed Cypher labels was removed.
- **No benchmark runner in the repo.** Writing it would have needed `raven_log`. Its results are in the Phase 0 table, and its queries became the production `graph_*.sql` files.
- **`after_graph_change` and `graph_counts` live in `graph/changes.py`.** The pipeline stage keeps the name `project` so old checkpoints still resume.
- **Transitive closure runs over asserted edges only**, 2 to 4 hops, never chaining on its own output.
- **Two more existing bugs found, fixed in this PR:** the purge endpoint (`aryx_run.id` / `aryx_job.id`, plus a skipped first DELETE) and `ActionStore.set_attribute` (`Json` where `Jsonb` is needed). Regression tests in `tests/e2e/test_purge_and_set_attribute.py`.

**Raven logging.** No `raven_log` was added (your decision). Raven's write-time hook refuses new Python with database calls and no `raven_log`, so with your explicit approval about 30 files were created or edited through the shell instead of the Write and Edit tools: `store/inferred_store.py` and `graph/changes.py` (new); `reasoning/engine.py`, `reasoning/edge_axioms.py`, `graph/pg_reader.py`; the `graph_url` and `after_graph_change` edits across `cli.py`, `pipeline/*`, and `api/*`; and a few smaller edits. Reviewers should know those files bypassed that hook. The commit gate is satisfied by a baseline (`.raven/decision-map-baseline.json`, 463 findings, 3 of them in the new code) written with the change staged. Its entries are keyed by file, line and symbol, so re-run `decision-map-gate.py --write-baseline` if any Python line moves before the commit.

## Inventory: every FalkorDB use

FalkorDB is referenced in 12 groups: one module, one projector, the ports seam, 14 direct `FalkorStore(...)` constructions, `graph_url` plumbing, the read consumers, infra, scripts, web, tests, docs and source text. Line numbers are from the current `main`.

### A. Core module `src/aryx/graph/`

| File | What it does | Action |
| --- | --- | --- |
| `falkor_store.py` (147 lines) | Writer: `clear`, `add_entity` (type labels + IRI), `add_provenance`, `remove_entity`, `add_relationship`, `counts`. Holds `_display_name` and `_safe_labels` | Delete. Port `_display_name` to SQL |
| `reader.py` (161) | `GraphReader`: `get_entity`, `find_entities`, `neighbors`, `all_relationships`, `provenance`, `count_by_relationship`, `shortest_path` | Replace with a Postgres reader |
| `retrieve.py` (97) | Ask retrieval (`gather`, `render_context`, `all_types`); only type-hints `GraphReader` | Keep logic, change import |
| `__init__.py` | Exports `FalkorStore`, `GraphReader` | Export the new reader only |

### B. Projection (the Postgres to graph copy)

| File | What it does | Action |
| --- | --- | --- |
| `project.py` (149) | `project_graph` (wipe and rebuild), `project_incremental`, `project_auto`, `_entity_iri`. Only `project_graph` is ever called; the other two have no callers | Delete. Replace with one `after_graph_change()` helper |
| `store/projection_store.py` (93) + 8 SQL files: `select_projection_state`, `upsert_projection_state`, `select_dirty_entities`, `select_tombstones`, `upsert_projected_entity`, `remove_projected_entity`, `select_provenance_for_entities`, `select_relationships_for_entities` | Watermark, dirty set and tombstones for the unused incremental path | Delete code, and drop the tables `aryx_projection_state` and `aryx_projected_entity` (cleanup migration 0048). `count_entities.sql` stays |
| `pipeline/enrich.py` `_build_type_ancestors` | Computes ancestor type names used only as Cypher labels. No reader uses labels | Delete once its 5 callers go; then check `ontology_store.py:102` for other users |

### C. Ports seam `src/aryx/ports/`

| File | What it does | Action |
| --- | --- | --- |
| `config.py:21-22` | Default adapters `aryx.graph.reader:GraphReader` and `aryx.graph.falkor_store:FalkorStore` | Point reader at the new class; drop `graph_store` |
| `container.py:36-46` | Builds adapters with `(graph_url, ws_graph(workspace_id))` | Build with `(rdb_dsn, workspace_id)`; remove `graph_store()` |
| `protocols.py:20-45` | `GraphReaderPort`, `GraphStorePort` | Keep the reader port; remove the store port |
| `naming.py`, `workspaces.py:11` | `ws_graph()` helper and its re-export | Remove once no caller is left |

### D. Direct FalkorDB constructions and mutations (14)

| Site | Today | After |
| --- | --- | --- |
| `pipeline/orchestrate.py:221` | `run_pipeline` stage `project` calls `project_graph` | `after_graph_change()`. Keep the stage name `project` (`checkpoint_store.py:25-26`) |
| `pipeline/orchestrate.py:263` | `link_entities` reprojects after FK edges | Same |
| `pipeline/derive_entities.py:132` | Reproject after deriving entities | Same |
| `pipeline/dimension_materialize.py:70` | Reproject after dimension links | Same |
| `api/corrections_api.py:82` | `_reproject` after a correction | Same |
| `api/adjudication_api.py:55` | `_reproject` after an approved merge | Same |
| `api/data_api.py:133` | `_reproject` for `POST /data/relate` (`reproject` flag) | Same. Keep accepting the flag |
| `api/workspace_api.py:159, 176, 191, 207` | reset-data, nuke, purge and delete each call `FalkorStore.clear()` | Remove. Add the new inferred tables to the delete lists |
| `api/system_api.py:62` | Status reads graph node and edge counts | Remove the `falkordb` block |
| `reasoning/engine.py:110` (+ `edge_axioms.py`) | Rule engine writes through `graph.run()` | Rewrite on SQL (see defects) |
| `api/graph_api.py:39-54` | `POST /graph/cypher` | Return 410, delete next release |

### E. `graph_url` plumbing (argument only)

`config.py:22` (Settings field) · `cli.py:42, 79` · `pipeline/orchestrate.py:117` (`run_pipeline`), `:235` (`link_entities`) · `pipeline/derive_entities.py:89` · `pipeline/dimension_materialize.py:52, 82, 100, 107` · `pipeline/dimension_entities.py:41, 80` · `pipeline/doc_discovery.py:272, 301, 308` · `api/file_ingest_api.py:339, 353, 361, 405` · `api/jobs_api.py:81` · `api/admin_api.py:93` · `api/connect_api.py:88` · `api/pipeline_link_api.py:53` · `api/pipeline_derive_api.py:45`.

Action: remove the parameter from 6 function signatures and about 20 call sites. A leftover `ARYX_GRAPH_URL` in an existing `.env` is safe: `Settings` uses `extra="ignore"` (`config.py:13-16`).

### F. Read consumers

| Site | What it does | Action |
| --- | --- | --- |
| `api/ask_api.py:67`, `ask_overview.py`, `lab_api.py:16-52` | Ask and Accuracy Lab: `all_types`, `gather`, overview via `find_entities(limit=500)` | Swap reader, no logic change |
| `api/graph_api.py` (`/entities`, `/graph`, `/neighbors`, `/provenance`, `/path`) | HTTP read API. MCP `entities_preview` calls `GET /graph` (`mcp/ingest_hitl.py:88`) | Swap reader, responses unchanged |
| `api/observability_api.py:53` | `_graph_stats` returns `len(find_entities(limit=500))`, so it caps at 500 | Replace with real `COUNT` queries |
| `analysis_execution/run.py:265`, `post_execution_validation/recompute.py:38`, `execute.py:381-391` | `graph_relation_count` nodes call `count_by_relationship` | Swap reader |

The web graph view uses `/data/graph` (`apps/web/lib/api.ts:77, 82`), which already reads Postgres through `EntityStore`.

### G. Infra and config

| File | Reference | Action |
| --- | --- | --- |
| `requirements.txt:11-12` | `falkordb~=1.0` | Remove |
| `docker-compose.yml:23-28, 174` | `falkordb` service, `graphdata` volume | Remove |
| `docker-compose.yml:38, 102, 135` | `depends_on: falkordb` for worker, api, mcp | Remove |
| `docker-compose.yml:1-3, 41` | Comments | Reword |
| `.env.example:8` | `ARYX_GRAPH_URL=redis://falkordb:6379` | Remove (needs a human; file is guarded) |
| `.github/workflows/ci.yml:39, 59-62, 81, 100` | e2e job name, `falkordb` service, `ARYX_GRAPH_URL`, `ARYX_TEST_GRAPH_URL` | Remove |
| `pyproject.toml:38` | Pytest marker text | Reword |
| `SECURITY.md:30` | "Do not publish Postgres/FalkorDB ports" | Reword |

`Dockerfile` and `Makefile` have no FalkorDB reference (checked).

### H. Scripts

| File | What it does | Action |
| --- | --- | --- |
| `scripts/seed_demo.py` | Writes entity names and sample edges straight into FalkorDB (graph-only state) | Rewrite against Postgres with `EntityStore` |
| `scripts/seed_support.py`, `scripts/patch_ticket_names.py` | One-off demo patches with hard-coded host `falkordb` | Delete (nothing references them) |

### I. Web `apps/web`

| File | Reference | Action |
| --- | --- | --- |
| `lib/api.ts:641-660` | `systemStatus` type has a `falkordb` block | Remove the block |
| `components/jobs/SystemStatus.tsx:20, 48, 81` | FalkorDB status dot and per-workspace Graph column | Remove both |
| `app/page.tsx:284` | Reset confirm text: "and its whole FalkorDB graph" | Reword |
| `app/observe/page.tsx:18`, `lib/api.ts:614` | Comments | Reword |

### J. Tests

| File | Reference | Action |
| --- | --- | --- |
| `test_ports_seam.py:23-24, 39-56` | Asserts default adapter paths and constructor args (`aryx_ws_7`) | Rewrite |
| `test_protege_parity.py:11, 15, 81-125` | Imports `_safe_labels`, `_entity_iri`; Cypher-capturing fake for the axiom tests | Rewrite axiom tests for SQL; drop label tests |
| `test_derive_entities.py:22-26` | Patches `FalkorStore`, `project_graph`; passes `graph_url` | Update |
| `test_actions.py:8`, `test_pool.py:9`, `test_auth.py:12`, `test_understanding.py:20`, `test_smart_understand_brief_led.py:16`, `test_mcp_security.py:25`, `test_histogram_contract.py:23` | Stub `falkordb` in `sys.modules` | Remove the entry |
| `tests/e2e/conftest.py:25, 32, 48-51`, `test_e2e_transactional_bypass.py:115-187`, `test_e2e_ingest_hitl_loop.py`, `test_e2e_auto_chain.py`, `test_e2e_mcp_tools_to_db.py`, `test_e2e_correction_roundtrip.py` | Real FalkorDB fixtures and docstrings. These exercise the write-then-read path | Update. They become the main regression guard |
| `test_analysis_execution.py:694-718`, `test_post_execution_validation.py:360` | `_FakeGraphReader` at port level | Comment only |

### K. Docs

- **Update (living docs):** `README.md` (lines 24, 194, 221, 265), `CONTRIBUTING.md:26`, `docs/ARCHITECTURE.md`, `FEATURES.md`, `INSTALL.md`, `HANDOFF.md`, `EDITIONS.md`, `DOCKERHUB.md`, `INGESTION_GUIDE.md`, `Ontology_Detailed.md`, `ontology_reasoning_readme.md`, `guides/DEVELOPER_GUIDE.md` and `.html`, `README.html`, `mcp-guide.html`, `diagrams/technical-flow.html`, `wiki/STATE.md`, and a new entry in `wiki/DECISIONS.md` superseding DEC-001. Add the release entry to `CHANGELOG.md`.
- **Leave as history:** older `CHANGELOG.md` entries, `docs/plan_*.md`, `doc_delta*.md`, `C01-C08_status.md`, `eda-profiling-*`, `ingestion-pipeline-flow-speaking-script.md`, `e2e_regression_testing_report.md`, `wiki/gaps/G8.md`, `G13.md`, `wiki/sources/gap_map.md`, and migrations 0009 and 0012 (earlier migrations are never edited).

**Not searchable by grep, checked by hand:** `docs/eda-profiling-system-documentation.docx` has 4 FalkorDB mentions, and the diagrams `docs/images/graph_write_minimization.png` and `docs/images/ingestion_flow.png` show a FalkorDB box. All three belong to historical docs, so leave them. `hub-lens-system-documentation.docx` and `unstructured_retrieval.png` have none. The other `docs/images` files were not opened. **Ownership rule:** `docs/wiki/STATE.md` is written only by the `aryx-conductor` agent, so ask that agent to record this change rather than editing the file by hand.

### L. Source text that mentions FalkorDB

`ask/evidence.py:4` · `reasoning/__init__.py:1` · `api/graph_api.py:1` · `api/system_api.py:4` · `api/data_api.py:128` · `api/adjudication_api.py:50` · `api/workspace_api.py:137` · `analysis_execution/execute.py:359`. One is user-visible to agents: `mcp/tools_onboard.py:30` says workspaces have their own "FalkorDB" graph in a tool description.

## Existing defects the migration must account for

The graph layer has 13 defects today, and five of them mean the reasoning engine has never worked. They were found by reading the code and git history; none has been run yet, and Phase 0 confirms each against a live stack.

| # | Defect | Where | What the plan does |
| --- | --- | --- | --- |
| 1 | `FalkorStore.run()` does not exist and never did (`git log -S"def run"` on the file is empty). `POST /graph/cypher` always fails with 400, and `POST /rules/evaluate` returns 500 as soon as a rule fires or an edge axiom exists | `reasoning/engine.py:56,66`, `edge_axioms.py:22,32,44`, `graph_api.py:52` | Rewrite the engine on SQL. Return 410 from the Cypher endpoint |
| 2 | Rule-created edges can never be seen. `_apply_edge` matches the target on property `ontology_type`, but nodes store `type`. It also writes `INF_<NAME>` edges, while every reader matches only `REL` | `engine.py:62-71`, `reader.py` | New table for inferred edges, read by the new reader |
| 3 | `set_label` writes `inferred_label` on a node that no reader returns. (The `inferred_label` the action engine writes at `actions/engine.py:99-100` is a separate Postgres attribute) | `engine.py:54-59` | New table for inferred labels, returned on entity reads |
| 4 | Axiom closures `MERGE` onto an existing edge and then `SET i.inferred = true`, so an asserted edge can be relabelled as inferred | `edge_axioms.py:22-24, 32-35, 44-48` | Separate table; insert only where no asserted edge exists |
| 5 | Inferred edges are wiped by every `project_graph` (it calls `clear()` first), so they vanish after any ingest, correction or merge until rules are re-run | `project.py:51` | Clear inferred rows at the same hooks, and document it |
| 6 | Duplicate edges are hidden today. `aryx_relationship` has no unique constraint and `insert_relationship.sql` is a plain `INSERT`. FalkorDB's `MERGE` collapses duplicates; Postgres reads would not | `0005`, `0009`, `insert_relationship.sql` | `SELECT DISTINCT` in the reader. A unique index is a separate follow-up (needs a dedupe first) |
| 7 | Dangling edges are hidden today. Migration 0009 dropped the foreign keys, and FalkorDB skipped any edge whose endpoint was missing | `0009_workspaces.sql` | Reader joins both endpoints to `aryx_entity` |
| 8 | The observability graph stat is capped at 500: it is `len(find_entities(limit=500))` | `observability_api.py:51-55` | Real `COUNT` queries |
| 9 | Factory reset clears graphs only for workspace ids 1, 2 and 3 | `workspace_api.py:174` | Disappears with the graph |
| 10 | Incremental projection (`project_auto`, `project_incremental`, `ProjectionStore`) has no callers, and its equivalence gate was never run (`docs/wiki/gaps/G8.md`) | `project.py:75-149` | Delete, no behaviour change |
| 11 | Node names are computed once at projection time, so attribute edits are invisible until a rebuild | `falkor_store.py:107` | Names computed live from the row |
| 12 | `select_provenance_for_entities.sql` joins `aryx_landed_record` on `id` only, unlike `select_members_provenance.sql`, which also joins `workspace_id` | `queries/` | In deleted code; the new provenance query joins on both |
| 13 | Entity-scoped rules crash before reaching the graph: evaluate\_workspace passes (id, type, attributes) tuples from list\_entities() to \_match, which calls .get() on them (found while implementing phase 3) | reasoning/engine.py:124 | Convert rows to {id, type, attributes} dicts in the rewrite |

## Target design on Postgres

Every graph read becomes a query on the existing `aryx_*` tables, scoped by `workspace_id` so Postgres prunes to one partition. There is no second copy and nothing to sync.

**Before:** ingest, correction or merge writes Postgres, then `project_graph` wipes and rebuilds FalkorDB, then readers query FalkorDB. **After:** the same writes go to Postgres only, and readers query Postgres.

### 1. Migration 0047 (additive only)

- **`aryx_display_name(attributes jsonb, entity_id bigint)`**, an `IMMUTABLE` SQL function that ports `_display_name` exactly: first truthy value of `name, full_name, title, label, ticket_ref, ref, sku, code, email, username`; else the first string value of 1 to 80 characters in stored key order (the order Python sees today); else `#<id>`. It is computed on read, with no stored column, so no write path can leave it stale.
- **`idx_rel_ws_name`** on `aryx_relationship (workspace_id, name)` for `count_by_relationship`. The source, target, type and member indexes from migration 0009 already exist.
- **`aryx_inferred_relationship`** and **`aryx_inferred_label`**, shown below.
- Migration 0047 is additive and drops nothing. The cleanup is a separate migration, 0048 (see Phase 4).
- Added because the benchmark demanded it (a name search with no match took 1.8 s without it and 0.6 ms with it): a `pg_trgm` GIN index on `lower(aryx_display_name(attributes, id))` for substring name search.

```sql
CREATE TABLE IF NOT EXISTS aryx_inferred_relationship (
    workspace_id     BIGINT NOT NULL,
    source_entity_id BIGINT NOT NULL,
    target_entity_id BIGINT NOT NULL,
    name             TEXT   NOT NULL,
    rule_name        TEXT   NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, source_entity_id, target_entity_id, name)
);
CREATE INDEX IF NOT EXISTS idx_inf_rel_ws_target
    ON aryx_inferred_relationship (workspace_id, target_entity_id);

CREATE TABLE IF NOT EXISTS aryx_inferred_label (
    workspace_id BIGINT NOT NULL,
    entity_id    BIGINT NOT NULL,
    label        TEXT   NOT NULL,
    rule_name    TEXT   NOT NULL DEFAULT '',
    PRIMARY KEY (workspace_id, entity_id)
);
```

These tables are not partitioned. They must be added by hand to every workspace delete path (see Phase 4).

### 2. New reader: `PostgresGraphReader`

Lives in `src/aryx/graph/pg_reader.py`, constructed as `(dsn, workspace_id)`, and borrows connections from `store/pool.get_pool`. All SQL goes in new `src/aryx/queries/graph_*.sql` files loaded with `load()`, because the repo forbids inline SQL.

| Method | How it is answered | Parity rule |
| --- | --- | --- |
| `get_entity` | One row by `(workspace_id, id)` | Name is the display name |
| `find_entities` | Optional exact type; optional case-insensitive substring on display name using `strpos(lower(..), lower(..))` (no `LIKE` wildcards to escape); limit clamped 1 to 500 | Same as Cypher `toLower(e.name) CONTAINS toLower($name)`. Adds `ORDER BY id` for a stable order |
| `neighbors` | Outgoing and incoming edges from `DISTINCT (source, target, name)`, both endpoints joined to `aryx_entity`, plus inferred edges | Same fields: id, type, name, relationship, direction |
| `all_relationships` | `DISTINCT` edges whose endpoints both exist, plus inferred edges | Same fields: source, target, name |
| `provenance` | `DISTINCT` system, dataset, record from members joined to landed records on `id` and `workspace_id`; the entity must exist | Same fields |
| `count_by_relationship` | `DISTINCT (source, target)` pairs for the named edge, both ends typed, grouped by the target's display name, direction out or in | Groups by name, not id, exactly like the Cypher. Empty result is `{}`, never an error |
| `shortest_path` | Breadth-first search, below | Same output shape |

**Shortest path.** A bidirectional, level-by-level breadth-first search in Python (forward along edges from the source, backward against edges from the destination, always expanding the smaller side), one query per level (`source_entity_id = ANY(frontier)` outbound, `target_entity_id = ANY(frontier)` inbound), with a visited set and parent map. Hops are clamped to 1–10. It keeps today's rule: one outbound and one inbound search, never mixed, keep the shorter, outbound wins a tie. Work is bounded by the edges touched, unlike a recursive CTE that enumerates every path. A frontier cap stops a runaway search with an explicit error instead of a false "no path". Phase 0 measured this on 100k entities and 1M edges: 6-hop p95 was 153 ms bidirectional against 2,454 ms for a one-sided search, and the two agreed on hop counts in 120 checked searches. Parallel edges between the same pair are named by the earliest-created edge (lowest id), which is what FalkorDB returned in the golden capture. An inbound result comes back in edge direction (destination first), not source-to-destination order, because that is what FalkorDB returns. A node to itself always returns no path, even through a cycle or self-loop. These three rules were found in phase 0, not assumed.

### 3. Reasoning engine on SQL

- `evaluate_workspace` runs in one transaction: delete this workspace's inferred rows, then apply every enabled rule.
- **inverse\_of, symmetric:** `INSERT ... SELECT` the reversed edge, `WHERE NOT EXISTS` an asserted edge with the same triple, `ON CONFLICT DO NOTHING`.
- **transitive:** for each hop from 2 to the depth (capped at 4), self-join the edge that many times with `a <> b`, insert if absent. This also fixes defect 4.
- **add\_relationship rule:** resolve the target by the real `ontology_type` column and display name (fixes defect 2), write the edge as `INF_<NAME>` into the inferred table.
- **set\_label rule:** upsert into `aryx_inferred_label`.
- Readers return inferred edges with `inferred: true` and entities with `inferred_label`. Both keys are additive.

### 4. The write side disappears

One helper, `after_graph_change(dsn, workspace_id)`, replaces every `project_graph(...)` call. It deletes the workspace's inferred rows (they may point at merged or deleted entities) and returns three `COUNT(*)` values under the same keys callers return today: `entities`, `provenance`, `relationships`. The counts keep the same meaning as before: all entities in the workspace, member rows joined to landed records, and raw `aryx_relationship` rows. Job summaries and API responses therefore keep their shape and numbers.

### 5. Contract changes

| Interface | Change |
| --- | --- |
| `/graph`, `/entities`, `/neighbors`, `/provenance`, `/path` | Unchanged, plus additive `inferred` on edges and `inferred_label` on entities |
| Ask and Accuracy Lab | Unchanged |
| `POST /graph/cypher` | 410 Gone for one release, then removed |
| `GET /admin/system/status` | `falkordb` key removed. Breaking for outside consumers; the web UI changes in the same release |
| `GET /admin/observability` | `graph` counts become exact (the 500 cap goes away) |
| Ports | Reader constructor becomes `(rdb_dsn, workspace_id)`. `GraphStorePort` and `Container.graph_store()` removed. `ARYX_ADAPTER_GRAPH_READER` still overrides, but outside adapters must adopt the new constructor |
| Pipeline functions | `graph_url` parameter removed. Job summary keys unchanged. Checkpoint stage `project` keeps its name so old checkpoints still resume |
| Settings | `graph_url` removed. A leftover `ARYX_GRAPH_URL` is ignored |

### 6. Behaviour changes to announce

- Results are always live. Today Ask and `/graph` lag until the next `project_graph`.
- Result order is stable (`ORDER BY id`). FalkorDB gave no order guarantee.
- Ancestor-type labels disappear. No reader used them; `find_entities(type=...)` stays exact-type.
- Inferred edges and labels persist until the next graph change, then are cleared. Re-run rules with `POST /rules/evaluate`, as today.

### 7. Performance and load

- Lookups by id, type, source, target and member are already indexed and start with `workspace_id`.
- Name search scans one workspace partition. The trigram index is the fallback.
- Ask and graph reads now share the process connection pool (`get_pool`, default max 10). Benchmark under concurrent Ask load and raise the pool size if needed.

## Change plan by phase

Work is eight phases on branch `feat/remove-falkordb-pg-graph`, about 11.25 developer days in total. The old FalkorDB code is deleted only after the new reader matches the golden outputs captured in phase 0. All work stays on that branch, nothing goes to `main` directly, and each phase ends in its own commit.

| Phase | What | Days | Exit gate |
| --- | --- | --- | --- |
| 0 | Safety net: golden outputs from live FalkorDB, plus a benchmark of the prototype SQL | 1.0 | Golden files committed; benchmark inside targets |
| 1 | Migration 0047, API startup migration, workspace delete paths | 1.0 | Migration applies twice cleanly; purge, nuke and delete clear the new tables |
| 2 | `PostgresGraphReader`, ports rewiring, exact counts | 1.5 | New reader matches the golden files |
| 3 | Reasoning engine and axioms on SQL | 1.5 | Rule tests pass with real Postgres |
| 4 | Remove the write side, `graph_url` and the old graph code; drop the unused projection objects (migration 0048) | 2.5 | `grep` for `falkor`, `graph_url`, `ws_graph` in `src/` is empty; migration 0048 applied twice leaves the schema unchanged |
| 5 | Status API, web, config, compose, CI, scripts | 1.0 | Stack boots with no FalkorDB; web typecheck passes |
| 6 | Tests rewritten and added (runs alongside phases 2 to 5) | 2.0 | Unit suite and e2e job green with no FalkorDB service |
| 7 | Docs, changelog, final verification and PR | 0.75 | Review checklist below passes |

Raven process on every phase: freeze `design.md` (scope and acceptance) before code, run `raven-signoff` before each commit, and add `raven_log()` calls on any new error or fallback branch. This change does contain `DROP` statements (migration 0048), so Raven's schema guard hard-blocks them until the commit message carries `[GUARD:ALLOW-SCHEMA-DROP]`. Approval for the drops has been given.

### Phase 0. Safety net (before any production code changes)

1. Start `postgres` and `falkordb` with `docker compose`, then seed one fixture workspace through the e2e fixtures. It must include: several types; two entities with the same display name; duplicate edges; a dangling edge (target id not in `aryx_entity`); a self-loop; a cycle; attributes with `0`, `""`, a list, an 81-character string and non-ASCII text; and more than 500 entities.
2. Capture golden outputs. Project the fixture into FalkorDB, run all 7 `GraphReader` methods, and save each result as JSON under `tests/fixtures/graph_golden/`. After FalkorDB is removed, the new reader is checked against these files permanently, with no FalkorDB needed.
3. Add `scripts/bench_graph_pg.py`. It loads synthetic graphs (10k and 100k entities, up to 1M edges) into Postgres and times the prototype SQL for lookups, name search, neighbours, `count_by_relationship` and frontier expansion at 3, 6 and 10 hops.
4. Agreed targets: lookup and neighbours p95 under 20 ms; name search under 150 ms at 100k entities; 6-hop shortest path under 500 ms at 1M edges.
5. If a target is missed, add the trigram index or revisit the design before phase 2.

**Phase 0 results** (100,000 entities, 1,000,000 edges, one local Postgres 16; a throwaway database, not production hardware):

| Case | p95 before fixes | p95 with fixes | Target | Fix |
| --- | --- | --- | --- | --- |
| Entity lookup by id | 0.8 ms | 0.8 ms | 20 ms | none needed |
| Neighbours (random entity) | 2.0 ms | 2.0 ms | 20 ms | none needed. Hub entities with hundreds of neighbours reach about 100 ms |
| Name search, common word | 16.7 ms | 16.3 ms | 150 ms | none needed |
| Name search, no match | 1,848 ms | 0.8 ms | 150 ms | `pg_trgm` index |
| Type plus name search | 257 ms | 41 ms | 150 ms | `pg_trgm` index |
| 6-hop shortest path | 2,454 ms | 153 ms | 500 ms | bidirectional search |
| `count_by_relationship` | 418 ms | 418 ms | none set | tried a cheaper form: only 13% faster (377 to 327 ms), so the simple query stays |

The golden file is committed to the working tree and is identical across three separate capture runs in different workspaces.

### Phase 1. Migration and lifecycle

1. Add `src/aryx/store/migrations/0047_graph_on_postgres.sql` with the function, the index and the two tables from the design.
2. The API does nothing at startup today (`api/main.py:61-62`). Migrations run in the worker (`python -m aryx`) and in some endpoints, and compose does not make the API wait for the worker. Add `apply_migrations` to the API lifespan, and add a pg\_advisory\_lock around the work in `store/migrate.py` (it has none today, checked), so two services starting together cannot run migrations at once.
3. Add two delete queries (`delete_inferred_relationships_by_workspace`, `delete_inferred_labels_by_workspace`) and call them from all four paths that remove workspace data: `queries/purge_workspace_data.sql`, `queries/nuke_system.sql` (the `TRUNCATE` list), `WorkspaceStore.delete` in `workspaces.py`, and `reset_workspace_data` in `workspace_api.py`.

### Phase 2. Reader and ports

1. Add `graph/pg_reader.py` and the `graph_*.sql` files: entity by id, find, neighbours, all relationships, provenance, count by relationship (out and in), frontier expansion (out and in), entity labels by ids.
2. `ports/config.py`: default `graph_reader` becomes `aryx.graph.pg_reader:PostgresGraphReader`; drop `graph_store`. `ports/container.py`: construct with `(settings.rdb_dsn, workspace_id)`; delete `graph_store()`. `ports/protocols.py`: delete `GraphStorePort`. Update the `ports/__init__.py` exports and docstring.
3. Re-type `graph/retrieve.py`, `api/ask_overview.py` and `api/graph_api.py` against `GraphReaderPort`.
4. `api/graph_api.py`: `POST /graph/cypher` returns 410.
5. `api/observability_api.py:_graph_stats`: use `count_entities` and `count_relationships`.
6. Leave the old Falkor modules in place so the parity test can still run.

### Phase 3. Reasoning engine

1. Add `store/inferred_store.py` with methods to clear a workspace, apply inverse, apply symmetric, apply transitive, add an inferred edge, and set a label. SQL lives in new `queries/inferred_*.sql` files.
2. Rewrite `reasoning/engine.py` (`_apply_label`, `_apply_edge`, `_fire`, `evaluate_workspace`) and `reasoning/edge_axioms.py` to call the store inside one transaction.
3. Keep the rule DSL, `_match` (re-exported by `actions/engine.py:18`) and the HTTP response shape of `POST /rules/evaluate` unchanged.

### Phase 4. Remove the write side

| Edit | Files |
| --- | --- |
| Add `graph/changes.py` with `after_graph_change(dsn, workspace_id)` | new |
| Replace `project_graph(...)` with `after_graph_change(...)` | `pipeline/orchestrate.py` (2), `pipeline/derive_entities.py`, `pipeline/dimension_materialize.py`, `api/corrections_api.py`, `api/adjudication_api.py`, `api/data_api.py` |
| Remove the `graph_url` parameter and every argument passing it | The 6 signatures and \~20 call sites listed under inventory E |
| Remove the four `FalkorStore(...).clear()` calls and `ws_graph` imports; add the inferred deletes | `api/workspace_api.py` |
| Remove `_graph_status` and the `falkordb` key | `api/system_api.py` |
| Delete files | `graph/falkor_store.py`, `graph/reader.py`, `project.py`, `store/projection_store.py`, the 8 projection SQL files |
| Delete `_build_type_ancestors` and its 5 imports; delete its `ontology_store` method only if nothing else calls it | `pipeline/enrich.py`, `ontology_store.py` |
| Remove `ws_graph` | `naming.py`, `workspaces.py:11` |
| Remove `Settings.graph_url` | `config.py:22-25` |
| Reword the agent-visible tool text | `mcp/tools_onboard.py:30` |

After this phase, `grep -rniE "falkor|graph_url|ws_graph" src/` must return nothing except the 410 message and the changelog text.

### Cleanup migration 0048 (inside phase 4)

Migration 0048 removes the objects that only the deleted projector used: the tables `aryx_projection_state` and `aryx_projected_entity`, and the column `aryx_entity.updated_at`. They hold only bookkeeping that is rebuildable or unused.

**Why a plain drop would not stick.** `apply_migrations` re-runs every `.sql` file on every call, with no version table (`store/migrate.py`), and many endpoints call it. Migration 0022 re-creates all three objects on each pass, so a drop placed after it would re-run on every request and lock `aryx_entity` each time.

1. **Edit `0022_projection.sql`** so it no longer creates the two tables or adds `updated_at`, leaving a comment that points to 0048. This breaks the "never edit earlier migrations" rule on purpose; it is the only way the drop stays dropped. It is safe here because migrations are re-run rather than tracked.
2. **Add `0048_drop_projection_objects.sql`** with existence-guarded `DO` blocks (the pattern migration 0009 already uses): drop each table only if it exists, and drop the column only if it exists. After the first run, every later pass is a no-op that takes no table lock.
3. **Remove every reference:** `queries/purge_workspace_data.sql` lines 9-10, `queries/nuke_system.sql` line 7 (the `TRUNCATE` list), and the `updated_at = now()` line in `queries/update_entity_attributes.sql`. That query is live: `store/action_store.py:124` and `store/adjudication_merge.py:98` call it. Reword the docstrings at `actions/engine.py:7` and `store/action_store.py:121`.
4. **Raven's schema guard hard-blocks `DROP` statements** and may also block writing the file. The commit message must carry `[GUARD:ALLOW-SCHEMA-DROP]`, and you approve the block when it fires.
5. **Data lost:** the projection watermark, the projected-id list and the `updated_at` values. All were used only by code that is being deleted.

### Phase 5. Status, web, config, infra

See the next section. It is one commit so the stack boots without FalkorDB at the end of the phase.

### Phase 6. Tests

See the test plan. Write each test in the phase that introduces the behaviour, not at the end.

### Phase 7. Docs and final verification

Update the living docs, add the changelog entry and the DEC-001 superseding decision, then run the checklist in the test plan and open the PR.

## Infra, config, web and scripts: target state

After phase 5 the stack has no graph service and nothing in the repo reads a graph URL. The inventory lists where each edit is; this section says what each place looks like afterwards.

- **Compose:** `falkordb` service, `graphdata` volume and the three `depends_on: falkordb` entries are gone; `api`, `worker` and `mcp` keep waiting on a healthy `postgres`. Port 6379 is no longer published. The header comment says graph queries run on the relational store.
- **Dependencies:** `falkordb` leaves `requirements.txt`. No other code imports `redis` (checked), so the transitive client goes with it.
- **Settings and env:** `Settings.graph_url` is removed. Someone with access must delete `ARYX_GRAPH_URL` from `.env.example`, since Raven blocks edits to `.env*`.
- **CI:** the e2e job becomes "E2E tests (real Postgres)" with the `falkordb` service and the `ARYX_GRAPH_URL` and `ARYX_TEST_GRAPH_URL` variables removed. A new unit test fails the build if `src/` imports `falkordb` or mentions `FalkorStore`, or if `requirements.txt` lists `falkordb`.
- **Web:** `SystemStatus.tsx` drops the FalkorDB dot and the Graph column, leaving Workspace, Records, Entities and Links. The reset confirmation says the data is removed "from Postgres". The `systemStatus` type loses its `falkordb` block.
- **Scripts:** `seed_demo.py` is rewritten to set names and insert sample edges through `EntityStore`, so it no longer creates graph-only state. `seed_support.py` and `patch_ticket_names.py` are deleted.
- **Docs:** in `ARCHITECTURE.md`, change the core principle (line 7), the ports paragraph (37-44), pipeline step 7 "Project" (133, becomes "Finalise"), the projection section (156-163), the API table (171), the FalkorDB section (253+), the stack table (273) and DEC-001 (283). Add a new decision, "graph served from Postgres", under the next free DEC number, superseding DEC-001's wording. In `README.md` remove the graph badge (line 24). In `EDITIONS.md`, Lite becomes Postgres and Ollama, and the Oracle row says to swap the Postgres graph reader through the reader port.
- **Images:** compose pins `giggsodocker/aryx-lite` and `aryx-lite-web` at 1.9.0 (lines 32, 71, 114, 143). Both images must be rebuilt, because the web UI and the API change together. The version number is the release owner's call.

### Upgrade steps for existing deployments

1. Pull the new images and run `docker compose up -d --remove-orphans`. The old `falkordb` container is removed.
2. Migration 0047 applies on start. No data migration is needed, because FalkorDB held only a copy.
3. A leftover `ARYX_GRAPH_URL` in `.env` is ignored, so removing it is optional.
4. If rules are used, run `POST /rules/evaluate` once; inferred edges are rebuilt on demand.
5. After checking the new stack, the `graphdata` volume can be deleted to reclaim space. This is destructive and optional; it is a rebuildable copy.

## Test plan

The unit suite must stay green with no FalkorDB, the tests listed under inventory J are rewritten, and eleven test groups are added or rewritten, with the golden files as the main safety net. The golden files are captured once from live FalkorDB in phase 0, so the new reader is held to today's behaviour after FalkorDB is gone.

### New tests

| Test | What it proves |
| --- | --- |
| `tests/e2e/test_graph_golden.py` | All 7 reader methods on the fixture workspace match `tests/fixtures/graph_golden/*.json`. Includes `gather` and `render_context` output for fixed Ask terms, so the text the LLM reads does not change |
| `tests/test_pg_graph_reader.py` | Limit clamped to 1–500 and hops to 1–10; `%` and `_` in a name search are literal; empty results; `count_by_relationship` direction out and in |
| Breadth-first search unit test (in-memory adjacency, no database) | Shortest path, outbound wins a tie, cycles, self-loop, unreachable target, source equals target returns `[]`, frontier cap |
| `tests/e2e/test_display_name_parity.py` | `aryx_display_name` equals a Python reference copy of `_display_name` over about 500 generated attribute sets, including `0`, `""`, lists, 81-character strings, non-ASCII text and key-order cases. The reference lives in the test because `falkor_store.py` is deleted |
| `tests/e2e/test_inferred_edges.py` | Inverse, symmetric, transitive (depth cap 4, cycles), `add_relationship` rule and `set_label` rule. Asserted edges are never marked inferred. Re-running is idempotent. `after_graph_change` clears them |
| `tests/e2e/test_workspace_lifecycle_graph.py` | After reset-data, purge, delete and nuke, the reader returns nothing for that workspace and both inferred tables hold no rows for it. Other workspaces are untouched. A reader on workspace A never returns workspace B ids |
| `tests/test_after_graph_change.py` | Returns `entities`, `provenance`, `relationships` with the old meanings; clears inferred rows; imports no graph driver |
| API tests | `/graph/cypher` returns 410; `/admin/system/status` has no `falkordb` key; `/admin/observability` graph counts are exact above 500 entities |
| `tests/test_no_falkordb.py` | Fails if `src/` imports `falkordb`, mentions `FalkorStore`, or `requirements.txt` lists `falkordb` |
| Rewritten `tests/test_ports_seam.py` | Default reader path; constructor receives `(dsn, workspace_id)`; `ARYX_ADAPTER_GRAPH_READER` override still resolves; no `graph_store` |
| tests/e2e/test\_cleanup\_migration.py | On a database that still has the old tables and column (with rows in them), applying migrations removes them. Applying again changes nothing. A fresh database never creates them. Workspace purge, reset, nuke and entity attribute updates still run |

One more regression guard already exists: `tests/e2e/test_e2e_correction_roundtrip.py` retypes an entity and reads it back through `/graph`, which now goes through the new reader.

### Final verification checklist (phase 7)

- [ ] `bash scripts/run_unit_tests.sh` passes with no Docker services.
- [ ] `pytest -m "e2e and not e2e_llm" tests/e2e/ -v` passes against Postgres only.
- [ ] A grep for `falkor`, `graph_url`, `ws_graph` and `6379` across `src`, `scripts`, `tests`, `apps`, `docker-compose.yml`, `requirements.txt` and `.github` finds only the 410 message and historical docs.
- [ ] `docker compose up` starts with no `falkordb` container.
- [ ] Manual smoke on the demo workspace: ingest a sample CSV, ask two questions, open Data and Observe, run a shortest path, run `POST /rules/evaluate`, reset the workspace.
- [ ] The CI web typecheck job passes.
- [ ] Benchmark numbers from phase 0 are attached to the PR and meet the agreed targets.
- [ ] Raven gates pass: `raven-review`, `raven-security`, `pre-push-reviewer`.

## Rollout, rollback, risks and decisions

Ship without dual-running, because FalkorDB held only a copy. Rollback is reverting the release, and 11 risks are tracked below, each with a mitigation.

### Rollout

- **Decided: one pull request** for all eight phases, with each phase as its own commit so reviewers can step through it. Nothing reaches production before the whole change merges, so the golden files, parity tests and phase exit gates are what prove the new reader. They must not be skipped.
- **Release notes must list three breaking changes:** the `falkordb` key in `/admin/system/status`, `POST /graph/cypher` returning 410, and the removed `graph_url` setting and parameters.
- **Effort and contingency:** 11.25 developer days (phase table above), plus about 2 days of contingency, mostly for the shortest-path and name-search benchmark. The biggest uncertainty is phase 3: the rule engine has never run, so its expected behaviour comes from docstrings, not from observed output.

### Rollback

- Revert the PR and redeploy the previous images. Migrations are re-run on every start and are idempotent, so the old image's migration 0022 simply re-creates the dropped tables and column (empty; they held only rebuildable bookkeeping). Migration 0047's two new tables sit unused.
- To refill FalkorDB after a rollback, call `POST /data/relate` with `links: []`, `replace: false` and `reproject: true`. **Do not leave `replace` at its default of `true`: it clears every relationship first** (`data_api.py:109`).

### Risks

| # | Risk | Likelihood / impact | Mitigation |
| --- | --- | --- | --- |
| 1 | Shortest path is slow on dense graphs | Medium / Medium | Phase 0 benchmark gate; search bounded by a visited set; frontier cap; trigram index as fallback |
| 2 | SQL display name differs from the Python one | Medium / High (Ask quality) | About 500 generated parity cases plus golden files |
| 3 | Duplicate or dangling edges change counts or answers | Medium / Medium | `DISTINCT` and endpoint joins; the fixture contains both; golden files |
| 4 | A call site is missed | Low / High | Removing the dependency makes leftovers fail on import; guard test; inventory checklist |
| 5 | Ask answers change through ordering or names | Medium / Medium | `ORDER BY id`; golden `render_context` snapshot; compare real questions before and after |
| 6 | Ask and graph reads exhaust the connection pool | Medium / Medium | Load test; raise the pool maximum; statement timeout on graph queries |
| 7 | New tables missed in a workspace delete path | Medium / Medium | All four paths named in phase 1; lifecycle e2e test |
| 8 | API serves a request before migration 0047 has run | Medium / High on first boot | Apply migrations in the API lifespan; add an advisory lock to `migrate.py` |
| 9 | Outside users of the `falkordb` status key, `/graph/cypher` or a custom port adapter break | Low / Medium | 410 for one release; release notes; adapters adopt the new constructor |
| 10 | Docs drift | High / Low | Phase 7 checklist and grep |
| 11 | Raven's schema guard blocks the DROP statements | Medium / Low | Commit message carries \[GUARD:ALLOW-SCHEMA-DROP\] with your explicit approval; the drops touch only unused objects and are guarded by existence checks |
| 12 | Migrations re-run on every call, so the dropped objects could be re-created, or the drop could repeat and lock aryx\_entity | Medium / Medium | Edit 0022 so it stops creating them; guarded DO blocks make 0048 a no-op after the first run; a test proves a second pass changes nothing |

### Decisions (all ten questions closed)

Five questions follow the recommendation in the original plan, four use the defaults the plan already stated, and one (the version number) is deliberately left to the release owner.

| # | Question | Decision |
| --- | --- | --- |
| 1 | Inferred edges and labels in normal reader output | Yes. Returned in normal output, flagged `inferred: true` on edges and `inferred_label` on entities |
| 2 | `shortest_path` direction | Keep today's directed search for parity. Undirected is a later change |
| 3 | `POST /graph/cypher` | Return 410 for one release, then delete it |
| 4 | Phase 0 targets and design scale | Agreed as proposed: lookups and neighbours p95 under 20 ms; name search under 150 ms at 100k entities; 6-hop shortest path under 500 ms at 1M edges. Design scale is the benchmark's top size, 100k entities and 1M edges per workspace (an assumption, since no real workspace size was given) |
| 5 | `pg_trgm` | Not added up front. Add it only if the name-search benchmark misses its target, and only after checking that the managed Postgres allows the extension. Accepted by you. Phase 0 result: no-match name searches missed the target (1.8 s), so the index is added in migration 0047; if the extension is unavailable the migration skips it and search still works, only slower |
| 6 | Seed scripts | Rewrite `seed_demo.py` on Postgres; delete `seed_support.py` and `patch_ticket_names.py` |
| 7 | Pull requests | One pull request |
| 8 | Version number | Not decided here. The release owner picks it at release time; the breaking changes are called out in the release notes. Does not block the work |
| 9 | Cleanup migration for `aryx_projection_state`, `aryx_projected_entity`, `updated_at` | Done in this pull request as migration 0048, with schema-drop approval given. The commit message must carry \[GUARD:ALLOW-SCHEMA-DROP\] |
| 10 | Display names | Keep the two rules (`explore.display_name` and `_display_name`) as they are. Unify later |
