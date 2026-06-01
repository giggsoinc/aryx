# Aryx — Engineering Handoff

Paste-ready context for a fresh Claude Code session. Keep this current as the codebase moves.

---

## 0. Coordinates

| | |
|---|---|
| **Project** | Aryx — knowledge-graph platform (Python 3.13, FastAPI, FalkorDB, Postgres+pgvector, Ollama) |
| **Repo** | https://github.com/giggsoinc/aryx.git (branch `main`) |
| **EC2** | `ec2-user@ec2-3-91-73-197.compute-1.amazonaws.com` · key `~/.ssh/rvdts-oracle-key.pem` |
| **Local dir** | `/Users/giggso/AntiGravity_Projects/Aryx` |
| **EC2 app dir** | `/home/ec2-user/aryx` (real git clone via read-only deploy key) |
| **Live** | UI `http://3.91.73.197:8501` · REST API `:8088` · MCP SSE `:8765` |

---

## 1. Non-negotiable working rules (learned the hard way)

1. **Deploy via git only.** Edit → commit → push → on EC2 `git pull && docker compose up -d`.
   Never `scp`, ad-hoc `docker run`, or manual `docker exec` for changes. Infra is code.
2. **Never `cd` in a Bash tool call.** Raven hooks resolve scripts by **relative** path; a
   persisted `cd` breaks every hook and locks all tools. Use absolute paths / `git -C`.
3. **Raven pre-commit reads a stale `.git/COMMIT_EDITMSG`.** For deletions / schema drops the
   flag in `git commit -m` is not seen → write the message into `.git/COMMIT_EDITMSG`, then
   `git commit -F .git/COMMIT_EDITMSG`. Flags: `[GUARD:ALLOW-DELETE]`, `[GUARD:ALLOW-SCHEMA-DROP]`.
4. **Deployed pipeline must use a LOCAL-ONLY broker.** `default_broker()` bundles Anthropic
   specs (Haiku=cheap, Opus=frontier) that take priority but have no key → auth crash. Use
   `admin_api._local_broker()` (Ollama-only). Ask uses `llm_runtime` (same idea).
5. **`docker compose build` can serve stale code.** Use `--no-cache` + `--force-recreate`;
   verify with `docker exec ... grep` when behaviour doesn't match disk.
6. **Raven style discipline:** ≤150 lines/file, type hints + docstrings, no `print()`, SQL lives
   in `src/aryx/queries/*.sql` via `load("name")` (no inline SQL in `.py`), no secrets in git.
7. **Skill enforcement hook:** invoke the `raven:fastapi-specialist` skill before any file read /
   bash / code response, every turn.

---

## 2. Deploy procedure (copy/paste)

```bash
# after committing + pushing locally:
ssh -i ~/.ssh/rvdts-oracle-key.pem ec2-user@ec2-3-91-73-197.compute-1.amazonaws.com \
  "cd /home/ec2-user/aryx && git pull --ff-only && \
   docker compose build --no-cache api ui && docker compose up -d --force-recreate api ui"

# DB migrations run on ingest, or force them:
docker exec aryx-api-1 python -c \
 "from aryx.store.migrate import apply_migrations; from aryx.config import get_settings; apply_migrations(get_settings().rdb_dsn)"
```
EC2 `.env` holds `POSTGRES_PASSWORD`, `ARYX_RDB_DSN`, `ARYX_GRAPH_URL` (gitignored).
In-network hosts: `postgres:5432`, `ollama:11434`, `falkordb:6379`.

---

## 3. Architecture

- **UI** (Streamlit, `src/aryx/ui/`) talks **only** to the REST API. Thin clients auto-attach the
  active `workspace_id` to every scoped call:
  - `ui/api.py` — graph, ask, jobs, workspaces, llm-config, observability.
  - `ui/ingest_client.py` — db ingest, connect/discover, multi-table, docs summary/confirm.
  - `ui/ontology_client.py` — RDF/OWL config, formats, export, import.
  - `ui/upload.py` — multipart (file/folder + docs `read`).
  - Panels: `home, ingest, ask, graph, observability, settings, ontology` + `workspace_bar` (sidebar).
- **REST API** (`src/aryx/api/`, FastAPI). Routers wired in `api/main.py`: graph, admin,
  ask, jobs, file_ingest, connect, doc_discover, workspace, observability, **ontology**.
- **Pipeline** (`pipeline/orchestrate.run_pipeline`): discover → resolve → (relate / fk_link) →
  project. Threads `workspace_id` everywhere. `fk_edges.link_by_attribute` = full join (1-to-many).
- **Postgres = source of truth.** Resolution tables (`aryx_entity`, `aryx_landed_record`,
  `aryx_entity_member`, `aryx_relationship`) are **LIST-partitioned by `workspace_id`**.
- **FalkorDB = rebuildable projection**, **one named graph per workspace**: `aryx_ws_<id>`
  (`workspaces.ws_graph`). `GraphReader`/`FalkorStore` take a `graph=` arg.
- **LLM layer:** Broker (`src/aryx/broker/`) routes anthropic/ollama/openai-compatible by tier
  (frontier/mid/cheap/local) + token governor. `src/aryx/llm.py` = `complete_json` + `complete_text`.
  `src/aryx/llm_runtime.py` = runtime-swappable provider/model/key for Ask (Settings), logs every
  call to `aryx_llm_call`.

### Ollama models (on EC2, ~2 GB total, pulled by `ollama-init` in compose)
- `qwen3.5:0.8b` (988 MB) — menial+answer (Ask), term/type inference. Thinking-capable; run `think=False`.
- `lfm2.5-thinking` (731 MB) — opt-in deep reasoning (installed; not default — slow on CPU).
- `nomic-embed-text` (274 MB, dim 768) — document embeddings. `catalog.json` embed endpoint `http://ollama:11434`.
- Box is **CPU-only** (4 core, 15 GB RAM) → LLM stages take 10–60 s; `_post_json` timeout = 600 s.
  A cloud frontier key (Settings) makes Ask/discovery fast + higher quality.

---

## 4. What exists today (all on `main`; verify each is deployed on EC2)

- **UI**: Home/welcome, nav Home→Ingest→Ask→Graph→Observability→Ontology→Settings, theme.
- **Ask** (#5): LLM Q&A over the graph, chat memory, tool-call display, token/latency.
- **Settings**: pick provider (Local/Claude/OpenAI/Gemini) + paste key live; + ontology interchange toggle.
- **Pipeline progress** (#7): durable `aryx_job`/`aryx_job_event`, live stage %, 30-day archive.
- **Graph** (#6): interactive canvas, drill-down, search, type filter, hide-isolated, **path
  explorer** (`/entities/{a}/path/{b}` — FalkorDB needs `shortestPath` in WITH/RETURN, directed).
- **Observability** (#8): `/admin/observability` — jobs + LLM tokens/latency + graph counts.
- **Multi-source ingest** (#3): connection-first, **context-driven auto-discovery agent**.
  Multi-RDBMS via SQLAlchemy (Postgres/MySQL/MariaDB/Oracle/SQLite; SQL Server needs ODBC).
  `/admin/connect → /discover → /ingest/multi`. File/folder upload (JSON, CSV, PDF, PPTX, DOCX,
  images; ≤50 files, 2 MB each, 50 MB total). **Self-discovering documents** (no ontology fields):
  `/admin/docs/read → /summary → /confirm` (`doc_discovery.py`, `discoveries.py`, `records_source.py`).
- **Workspaces + partitioning**: isolate use-cases. `aryx_workspace` table, LIST partitions per
  workspace, named graph per workspace. Sidebar selector (`ui/workspace_bar.py`) switch/create/delete;
  Default (id 1) protected. Create attaches 4 partitions; delete drops them + clears the graph =
  instant physical purge. `/admin/workspaces` (GET/POST/DELETE). `migrate.py` parses dollar-quoted
  `DO` blocks. Verified E2E (create→ingest isolated→ws1 untouched→delete purges).
- **Ontology interchange (RDF/OWL)** — `api/ontology_api.py` (`/ontology/config|formats|export|import`),
  `ui/ontology_panel.py`, `ui/ontology_client.py`, uses **rdflib**. Export the graph for
  Protégé/GraphDB/Jena; import external ontologies. Toggle in Settings → adds an Ontology sidebar page.
- **Documentation suite** (locked #4/#1/#2) — in `docs/`: `ARCHITECTURE.md`, `INSTALL.md`,
  `USER_GUIDE.md`, `INGESTION_GUIDE.md`, `RDF_EXPORT_GUIDE.md`, `Ontology_Detailed.md`,
  demo files, and `docs/diagrams/{business-view,technical-flow}.html`.

---

## 5. Open / next

- **Raven audit+email gap** (separate Raven product, not Aryx code): guards block but never call
  `emit-violation`/`audit-log`/`approval-request`; `.raven/audit/` stays empty; manifest
  `shared_inbox` key mismatches `approval-request.py`'s `admin_email`/`smtp_*`. A fix-prompt for the
  Raven team was drafted earlier in history.
- **Multi-user collaboration** on workspaces (planned "later" — add users/roles per workspace).
- **SQL Server** driver (`pyodbc` + system ODBC). **Cloud frontier model** for discovery/answer quality.
- **PDF/DOCX mention path** not yet tested live end-to-end (same `DocumentRouterConnector` as Inc 8;
  read step just collects its output). Worth a real-document E2E.
- Legacy `create_app`/`app` at the bottom of `graph_api.py` is dead — `api/main.py` is the real app.

---

## 6. Quick test — workspaces (browser)

UI → sidebar **Workspace** dropdown → "Manage workspaces" → create e.g. "Sales".
Ingest tab → describe context → **Database** → connect (`host=postgres, port=5432, db=aryx,
user=aryx, password=<POSTGRES_PASSWORD from EC2 .env>`) → **Run discovery agent** → review → ingest.
Switch workspaces → data is isolated. Delete a workspace → physical purge. Default cannot be deleted.

**Start a new session by:** invoking `raven:fastapi-specialist`, reading `CLAUDE.md` +
`.raven/manifest.json` + this file, then `git -C <repo> log --oneline -20` to see the latest state.
