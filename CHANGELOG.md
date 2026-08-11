# Changelog

All notable changes to **Aryx Lite** are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.6.1] — 2026-08-11

### Fixed

- **Ollama model list 404** after using a cloud provider: switching to Ollama
  no longer keeps a Google/OpenAI base URL for `/api/tags`. `/llm/models` and
  health probe always use a local Ollama base. Home **Use this model** sends
  `endpoint=http://ollama:11434` when Ollama is selected.
- **Home model gate copy** — status lines no longer run together
  (`…by you` + provider); clearer “Saved choice” vs “Active engine”.
- **Settings** always shows **Software** block (product version, Python,
  platform) via `GET /version`.

## [1.6.0] — 2026-08-11

### Added

- **Home — delete workspace** for non-Default workspaces (id ≠ 1), with
  irreversible confirm (checkbox + type `DELETE`). Default remains protected
  server-side. (`app/page.tsx`, `api.deleteWorkspace`)
- **Home ModelGate — provider sample models** for Anthropic / Gemini /
  OpenAI / Grok (select + Custom…). (`lib/llmPresets.ts`, `app/page.tsx`)
- **Correct data coach** (was Fix by chat): intent chips, standing rules
  tab, selection from Table lens, empty-graph coach, real-data examples.
  (`CorrectionChat.tsx`, `TableLens.tsx`)

### Changed

- **Brief** — hand-authored six questions are primary; AI draft is optional
  and collapsed when a brief already has content. File chips state
  session-only / not stored. Save busy state always clears; draft overwrite
  confirms when fields are non-empty. (`BriefBuilder.tsx`)
- **Ollama ModelGate + Settings** — clearer empty-list error + Retry + custom
  name; polls while list is empty; cloud providers get sample model dropdowns
  + Custom (shared `lib/llmPresets.ts`). Save errors surface in the UI.
- **Graph lens** — selecting a node notifies Correct data coach (same as Table).

### Documentation

- USER_GUIDE nav and Brief / Correct data / workspaces; EDITIONS clarifies
  Lite polish vs Enterprise fork agentic plane; pack handoff under
  `Audit-Postmortem/packs/`.

## [1.5.3] — 2026-08-10

### Fixed

- **No Ollama dropdown anywhere in the real flow.** Two gaps: (1) the
  Settings page's model fields were always free-text — they are now
  dropdowns of installed local models whenever the provider is Ollama
  (live-fetched, loading/empty states, Retry, and a leftover cloud model
  name is never submitted as an Ollama model); (2) once a model was
  confirmed, the Home gate collapsed to a status line whose "change" just
  linked to Settings — it now re-expands the full inline picker in place.
  (`LlmSettings.tsx`, `app/page.tsx`)

## [1.5.2] — 2026-08-10

### Changed

- **Fix-by-chat proposes, never auto-applies.** The bot now answers every
  correction with a structured proposal ("Rename type X → Y. Apply?") and
  Apply/No buttons — a misparse costs one click, never a wrong edit. The
  applied action is the resolved structure, not the raw parse, so
  inverted-direction mistakes are impossible.
- **Chat drawer, not a mini-dock.** Full-height 420px side drawer with a
  larger transcript.

### Added

- **Type-level corrections.** New `rename_type` correction: renames the
  ontology type AND moves all its entities (one value — no duplicated
  key), stored as a standing rule ("the type X is now called Y") replayed
  into every ingest. The chat parser now knows the workspace's TYPE list
  next to the entity roster, with worked examples, and deterministically
  routes "‹Type› is ‹NewName›" to rename_type even when the model
  misclassifies. Verified on the exact reported scenario.
- **Helpful refusals.** "No idea" replies now say what the dock can do
  and how to phrase it, instead of a flat rejection.

## [1.5.1] — 2026-08-10

### Fixed

- **Ollama model list empty in the Home picker.** `/llm/models` asked the
  ACTIVE provider's endpoint for Ollama tags — with Gemini active it
  queried Google's API and returned nothing. It now always targets the
  local Ollama endpoint. Verified: full local model list returned while
  Gemini is the active provider. (`ask_api.py`)
- **Switching provider to Ollama showed no dropdown.** The picker fetched
  the model list once on mount and never refetched; it now refetches on
  every switch to Ollama, shows a loading state, an explicit "no local
  models — is Ollama running?" warning with Retry, and never submits a
  leftover cloud model name as an Ollama model. (`app/page.tsx`)

## [1.5.0] — 2026-08-10

### Added

- **The correction loop — point Aryx in the right direction.** Two ways,
  one audited path, every action both fixes the data NOW and stores a
  standing rule replayed into every future ingest (extraction context +
  post-relate enforcement):
  · **Click**: the Data entity panel gains retype (dropdown), merge-into,
    link-to, per-relationship unlink (✕), and remove-as-junk.
  · **Chat**: a "Fix by chat" dock on Data AND Model — "merge M. Lopez
    into Maria Lopez", "T-100 was resolved by Maria". The LLM only
    classifies the utterance; names resolve deterministically against the
    workspace roster; ambiguity asks back, questions are redirected to
    Ask (write-only surface, fully separate from Ask).
  Rules: retype · suppress · alias · pin_link · forbid_link, listable and
  deletable via /admin/workspaces/{id}/corrections.
- **Reset & re-ingest.** Home workspace card gains "↺ Reset & re-ingest":
  wipes the workspace's records/entities/links/profiles/jobs (Postgres)
  and its whole FalkorDB graph, with a confirm dialog showing exact
  counts. Brief, model choice, ontology types, and corrections survive —
  verified live. (`POST /admin/workspaces/{id}/reset-data`)
- **Quota failures fall back to local Ollama.** 429/RESOURCE_EXHAUSTED/
  connection failures on cloud providers transparently retry the call on
  the local Ollama models and log it loudly; auth errors (401/403) still
  surface immediately — a broken key is never silently masked.
- **First-screen LLM picker.** The Home gate is now a full inline picker:
  provider + model (auto-lists installed Ollama models via /llm/models) +
  key, verified before save, with the config source named explicitly
  ("source: environment file — not yet confirmed" → "set by you"). The
  bar renders only what the server echoes back — stale-provider display
  is impossible.

## [1.4.0] — 2026-08-10

### Added

- **Model choice is the first decision, and it sticks.** New Home gate:
  choose or explicitly confirm the language model (Ollama default) before
  anything runs — no silent defaults. The choice persists in Postgres
  (`aryx_llm_config`, migration 0028) with precedence UI > env file >
  Ollama default, so a container restart no longer reverts a UI-chosen
  provider. `/llm/config` reports `confirmed`. (`llm_runtime.py`,
  `app/page.tsx`)
- **Documents land TYPED and RELATED.** The upload path now lands doc
  entities per discovered type (Agent, Ticket, WorkflowStage… instead of
  everything as "Document"), registers those types in the ontology (Model
  canvas populates), and runs relationship inference across the workspace
  (capped) so edges appear in Data and the graph. Verified live: 4 types
  registered, 42 edges projected. (`api/file_ingest_api.py`)
- **Observe page** (`/observe`): jobs, workspace vitals, and physical
  storage truth as a first-class surface. Nav reordered to the product
  flow: Home · Brief · Data · Model · Lab · Ask · Observe · Settings.
  (`app/observe/page.tsx`, `Header.tsx`)
- **Brief remembers its sources.** Documents used to draft the brief are
  stored on it (`source_docs`) and shown on revisit. (`BriefBuilder.tsx`)

### Fixed

- **Relationship inference always returned nothing on Ollama.** The exact
  JSON shape was never shown to the model (schema isn't transmitted on the
  Ollama path), so models answered related=true with no name and every
  edge was skipped. Prompt now pins the exact shape. (`relationships.py`)

## [1.3.1] — 2026-08-09

### Fixed

- **Storage-truth panels went stale next to live job cards.** WorkspaceOverview
  and SystemStatus loaded once on mount; a job could finish (data landed)
  while the tiles kept showing zeros and "1 running". Both now refresh every
  10s while the panel is open and immediately when any job reaches a
  terminal state. (`WorkspaceOverview.tsx`, `SystemStatus.tsx`, `JobsBadge.tsx`)
- **Wizard claimed "reading your data… polling every 3s" forever.** The
  Running screen now flips to "Done reading your data." on complete and
  "This run failed." on failure. (`Running.tsx`)
- **Zero-extraction runs reported success.** When files were processed but
  not one entity landed (extraction model returning unusable output — still
  downloading, wrong provider, bad key), the job finished "complete —
  0 entities". It now fails with: "No entities were extracted… check the
  model in Settings and retry." Reproduced and verified live.
  (`api/file_ingest_api.py`)

## [1.3.0] — 2026-08-09

### Added

- **System status in the product (aryx_stat concept).**
  `GET /admin/system/status` reports physical storage truth straight from
  the stores: Postgres reachability + database size + per-workspace landed
  records / entities / relationships, document chunk + embedding counts,
  FalkorDB reachability + per-workspace graph node/edge counts, and LLM
  readiness. The jobs side panel now ends with a "Stored on this server"
  block showing all of it, refresh on demand — if a load claimed success
  but these read zero, the data did not land. (`api/system_api.py`,
  `graph/falkor_store.py` `counts()`, `components/jobs/SystemStatus.tsx`)
- **Zombie-job reaper.** Ingest runs as an in-process background task; a
  container restart killed it silently and the job claimed "running"
  forever. Listing jobs now first fails any running job with no checkpoint
  for 5+ minutes, with an actionable error ("process likely died — re-run
  the upload"), which also unlocks the Retry button.
  (`store/job_store.py`, `queries/reap_stale_jobs.sql`, `api/jobs_api.py`)

### Fixed

- **Brief now actually steers file ingest.** The wizard's upload path built
  its extractors with empty context — everything answered in the Brief
  (domain, aim, scope, objectives, proof questions) was ignored. The brief
  is now rendered into steering context and passed to document extraction
  and tabular type inference. (`api/file_ingest_api.py`)

## [1.2.2] — 2026-08-09

### Added

- **Model-readiness bar on the Brief step.** `GET /llm/health` probes the
  configured provider (for Ollama: are the models actually pulled?) instead
  of just echoing config. The Brief step opens with a green "Model ready —
  ollama · <model>" bar, or an amber bar with the reason (e.g. "still
  downloading models — first boot can take several minutes"), a Retry
  button, and auto-recheck every 10s. (`ask_api.py`, `BriefBuilder.tsx`)

### Fixed

- **Ingest status panel never appeared on the wizard.** The jobs side panel
  auto-opened only on Home and Model — not on /start or /data, where ingest
  actually runs and users stare at an unexplained wait. Now opens on all
  four (manual refresh button as before). (`JobsBadge.tsx`)
- **Brief doc upload felt like a black hole.** File tags now report
  "<name> — N characters read ✓" so it's obvious the document was read and
  will steer the draft. (`BriefBuilder.tsx`)

## [1.2.1] — 2026-08-09

### Fixed

- **Hardcoded URL prefix broke stock installs.** An externally-introduced
  deploy assumption baked a URL prefix into the web build — plain
  `localhost:3000` returned 404 everywhere, and two raw `<a>` anchors
  navigated outside the app entirely. The prefix is gone (app serves at `/`),
  and the anchors are proper `<Link>`s. (`next.config.mjs`,
  `apps/web/Dockerfile`, `components/model/Canvas.tsx`,
  `components/jobs/JobsBadge.tsx`)

## [1.2.0] — 2026-08-09

### Added

- **Landing home at `/`.** Root now lists every workspace with entity/link
  counts, brief status, and running jobs; blank slate drops straight into the
  wizard. Ask moved to `/ask`. (`apps/web/app/page.tsx`, `app/ask/page.tsx`,
  `components/brand/Header.tsx`)
- **Cruise-control Brief.** Wizard step 1 (replacing the single-box Goals +
  Confirm steps) and `/brief` now share one builder: drop PDF/DOC/DOCX/PPT
  documents (read for briefing only — never ingested as data) and/or one
  sentence; the configured LLM pre-answers all questions; the user confirms
  tap-chips and edits. Shows which model is drafting; warns with a Settings
  link when no LLM is reachable. (`components/brief/BriefBuilder.tsx`,
  `components/start/BriefStep.tsx`)
- **Sixth brief question — proof questions.** "What must this graph be able
  to answer?" drafted alongside the original five; stored on the workspace
  brief as `questions`. (`brief_draft.py`, `workspace_api.py`, `lib/types.ts`)
- **`POST /admin/workspaces/{id}/brief-doc-text`.** Extracts plain text from
  an uploaded briefing document via the existing PDF/DOCX/PPTX connectors;
  20 MB cap, 12k-char excerpt. (`api/brief_api.py`)

### Removed

- Wizard `Goals`/`Confirm` steps — superseded by the Brief step.

## [1.1.1] — 2026-08-09

### Fixed

- **Resolve stage crash on every run:** `'Settings' object has no attribute
  'max_block_size'`. The multi-key blocker read the block-size cap from
  Settings, but the field was never defined there. Added
  `max_block_size` (default 5000, env `ARYX_MAX_BLOCK_SIZE`). (`config.py`)

## [1.1.0] — 2026-08-09

### Added

- **Brief page restored** (`/brief`). The five-question grounding flow (domain,
  aim, objectives, scope, participant roles) is back as a Next.js page — lost
  when the Streamlit UI was removed in `926b51a`. Drafts all five fields from a
  one-line seed via the existing `draft-brief` API, persists via the workspace
  brief PATCH; Brief nav link precedes Onboard. No backend changes.
  (`apps/web/app/brief/page.tsx`, `apps/web/components/brand/Header.tsx`)

### Changed

- **Docker images are version-tagged only** — `1.1.0` · `v1.1.0` · git SHA;
  `latest` is no longer pushed or referenced. Compose defaults, docs, and
  `scripts/docker-hub-publish.sh` pin the semver tag (builds pinned to
  linux/amd64). Commercial contact is now support@giggso.com; invalid
  `mailto:` entry dropped from `pyproject.toml` `[project.urls]` (it broke
  `pip install -e .` on modern setuptools).

## [Unreleased] — 2026-08-08

### Fixed

- **Resolution O(n²) stall (production incident 2026-08-08).** `cluster_edges` and `survivors` each scanned the full `pair_scores` dict on every call — at 3,902 records × 1,295,202 pairs that was ~5 billion iterations, so stage 4/4 never completed. Fixed by inverting `pair_scores` once per run into an edge index `{record_id: [(other_id, score)]}` and threading it through `_materialize()`. Wall-clock for stage 4/4: hours → 459 ms. (`resolution/confidence.py`, `resolution/survivor.py`, `resolution/cluster.py`, `resolution/run.py`)
- **`KeyError: 'name'` in `infer_relationship` on tabular sources.** LLM returning `related=true` without a `name` field raised unconditionally. Now falls back gracefully to `(None, 0.0)` with a warning log instead of crashing the enrich stage. (`relationships.py`)
- **`adjudication budget exhausted` warning noise.** `ARYX_ER_MAX_ADJUDICATIONS` defaults to 0, so the WARNING fired on every run even when the budget was never configured. Now downgrades to INFO when the budget was never set; WARNING only fires when a configured budget is actually depleted. (`resolution/run.py`)

### Added

- **Per-workspace output panel in the Jobs side panel.** A new `WorkspaceOverview` section below the job cards shows each workspace's entity count, relationship count, landed records, and running-job indicator. Each workspace card has its own refresh button. (`apps/web/components/jobs/WorkspaceOverview.tsx`, `apps/web/components/jobs/JobsBadge.tsx`)
- **Post-ingest result card on the pipeline step.** When a job completes, `IngestResult` renders inline showing three independently refreshable blocks: records processed (from job events), what was discovered (entity types and counts), and connections mapped (relationship count). A collapsed "Diagnose this run" section expands the full event log on demand. (`apps/web/components/start/IngestResult.tsx`, `apps/web/components/start/Running.tsx`)
- **`GET /admin/workspace-overview` endpoint.** Returns per-workspace entity, relationship, landed-record, and running-job counts in a single call. (`src/aryx/api/observability_api.py`, `src/aryx/queries/count_landed.sql`, `src/aryx/queries/count_relationships.sql`, `src/aryx/queries/count_running_jobs.sql`)

---

## [Unreleased] — 2026-07-15

### Fixed

- **LLM `/draft-brief` 500 / 90s hang.** `ollama_json` ran full chain-of-thought
  on hybrid "thinking" models for pure JSON extraction (~70s/call), so brief
  drafting hung until the web proxy reset the socket. Disabled thinking on the
  Ollama JSON path (`think=false`) — 70s → 0.5s per call. (`llm_providers.py`)
- **Intermittent 500 on malformed LLM JSON.** A bare `json.loads` on model
  output raised whenever the local model emitted truncated/invalid JSON.
  Added a lenient parser (strict → outermost-object salvage → `{}`) so a bad
  response degrades to an empty result instead of a 500. (`llm_providers.py`)
- **Entity over-merge.** Records whose configured match key was absent produced
  empty match text; blank-vs-blank scored as a perfect duplicate, collapsing
  every row into one entity. Blank match text now scores 0, and
  `landed_records` falls back to whole-row text when keys miss.
  (`resolution/classical.py`, `store/entity_store.py`)
- **Everything typed "Document".** File upload applied one type/key pair to a
  heterogeneous batch. Each data file now infers its own entity type + match
  columns. (`api/file_ingest_api.py`, `pipeline/doc_discovery.py`)
- **`unhashable type: 'list'` during Resolve.** A nested `match_keys` list from
  LLM inference reached `payload.get(key)`. `match_keys` is now sanitized to a
  flat list of strings, and `landed_records` ignores non-string keys.
  (`pipeline/doc_discovery.py`, `store/entity_store.py`)
- **Resolve running for hours on large sources.** A bad inferred key forced
  whole-row matching, exploding pairwise scoring and LLM adjudication. Fixed
  with deterministic key repair (most-unique column), a per-run adjudication
  budget (default 0 — off), and skipping embeddings for short/keyed text.
  5,234 rows: hours → ~65s. (`api/file_ingest_api.py`, `resolution/run.py`)

### Added

- **Cross-file relationships on upload.** After all files land, foreign-key
  edges are discovered by value overlap + FK naming (no LLM), materialized via
  exact-match linking, and the graph is re-projected.
  (`pipeline/doc_discovery.py`, `pipeline/orchestrate.py`, `api/file_ingest_api.py`)
- **Entity-level graph.** `GET /data/graph?level=entity` returns per-entity
  nodes and edges. (`explore.py`, `api/data_api.py`)
- **Interactive graph UI.** React Flow + Dagre replaces the static SVG:
  draggable nodes, pan/zoom, minimap, working fullscreen, and a type legend.
  Large graphs use a hub-and-spoke cluster layout (company + its people) packed
  into a scrollable grid. (`components/data/GraphLens.tsx`, `lib/api.ts`,
  `lib/types.ts`)
- **Relationship exploration.** Click a node to highlight it, its neighbours,
  and the connecting edges (dimming the rest) and open a side panel with the
  entity's attributes, source records, and every relationship (label +
  direction); click a relationship to walk the graph. New
  `GET /data/entity/{id}`. (`explore.py`, `api/data_api.py`,
  `components/data/GraphLens.tsx`)
- **Graph search + type filters.** A search box locates and pans/zooms to any
  entity; legend chips toggle entity types on/off to declutter the view.
  (`components/data/GraphLens.tsx`)

### Changed

- **Observability.** Server entrypoints (API, MCP, Streamlit UI if present) now
  call `configure_logging()`, and the containers default to `DEBUG`.
  (`api/main.py`, `mcp/sse.py`, `docker-compose.yml`)
- **Resolution defaults for local models.** LLM adjudication and embedding-based
  scoring are now opt-in (fast, deterministic keyed resolution by default);
  enable via `ARYX_ER_MAX_ADJUDICATIONS` / `ARYX_ER_EMBED_MIN_CHARS`.
  (`resolution/run.py`)

## [1.0.1] — 2026-07-15

### Removed

- **Streamlit UI** (`src/aryx/ui/`, compose service `ui` on :8501, `streamlit` deps)
- `.streamlit/` theme config from the Python image

### Added

- **Next.js Settings** (`/settings`) — live LLM provider config (Ollama, Anthropic,
  OpenAI-compatible, Gemini, Grok/xAI) via `GET/POST` llm config API
- `ARYX_LLM_*` documented in `.env.example`

### Changed

- Primary UI is Next.js only; docs (README, INSTALL, ARCHITECTURE, FEATURES, USER_GUIDE) updated

## [1.0.0] — 2026-07-15

### Added

- **Business Source License 1.1 (BSL 1.1)** as the project license
  - Licensor: Giggso Inc.
  - Additional Use Grant: internal production use allowed; Competing Offering
    (multi-tenant / hosted commercial re-host) requires commercial license
  - Change Date: 2029-07-15 → GPL-3.0-or-later
- `LICENSE`, `NOTICE`, `docs/LICENSING.md`, `CONTRIBUTING.md`, `SECURITY.md`
- `pyproject.toml` package identity (`aryx` 1.0.0, BUSL-1.1)
- License metadata on web package (`apps/web/package.json`)

### Changed

- README and editions docs: MIT/GPL-candidate language replaced with BSL terms
- Version stamp: `aryx.__version__` → `1.0.0`

### Notes

- BSL is source-available, not OSI open source. See `docs/LICENSING.md`.
- Commercial licensing: support@giggso.com
