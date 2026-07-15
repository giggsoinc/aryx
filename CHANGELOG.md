# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

### Changed

- **Observability.** All three server entrypoints (API, MCP, Streamlit UI) now
  call `configure_logging()`, and the containers default to `DEBUG`.
  (`api/main.py`, `mcp/sse.py`, `ui/app.py`, `docker-compose.yml`)
- **Resolution defaults for local models.** LLM adjudication and embedding-based
  scoring are now opt-in (fast, deterministic keyed resolution by default);
  enable via `ARYX_ER_MAX_ADJUDICATIONS` / `ARYX_ER_EMBED_MIN_CHARS`.
  (`resolution/run.py`)
