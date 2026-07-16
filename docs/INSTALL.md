# Install Guide — Aryx Lite

Get Aryx running with Docker Compose (recommended), then open the web UI and onboard data.

| Doc | Audience |
|-----|----------|
| **This guide** | Operators and developers installing Aryx |
| [User guide](USER_GUIDE.md) | People using the product UI day to day |
| [Licensing](LICENSING.md) | BSL terms in plain English |

**Repository:** https://github.com/giggsoinc/aryx (public)

---

## Prerequisites

| Tool | Notes |
|------|--------|
| **Docker** + **Docker Compose** v2 | [Install Docker](https://docs.docker.com/get-docker/) |
| **Git** | Clone the repo |
| **RAM** | **8 GB+** recommended (Ollama pulls local models) |
| **Disk** | Several GB for images + model weights |
| Python 3.11+ / Node 20+ | Optional — only for non-Docker local development |

---

## 1. Clone

```bash
git clone https://github.com/giggsoinc/aryx.git
cd aryx
```

---

## 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` before production use. Important variables:

```bash
# Database (used by Compose to seed Postgres)
POSTGRES_PASSWORD=change-me-in-production
POSTGRES_DB=aryx

# App DSN — inside Compose network, host is "postgres"
ARYX_RDB_DSN=postgresql://aryx:change-me-in-production@postgres:5432/aryx
ARYX_GRAPH_URL=redis://falkordb:6379

ARYX_LOG_LEVEL=INFO

# LLM boot defaults (also changeable live in the UI under Settings)
ARYX_LLM_PROVIDER=ollama
ARYX_LLM_BASE_URL=http://ollama:11434
ARYX_LLM_MENIAL_MODEL=qwen3.5:0.8b
ARYX_LLM_REASON_MODEL=lfm2.5-thinking:latest
ARYX_LLM_API_KEY=

# API auth: off | optional (default) | required
# For any network-exposed deploy, use required and issue keys.
ARYX_API_AUTH=optional
```

**Never commit `.env`.** It is gitignored.

### LLM providers (optional)

Defaults use **Ollama** in Compose (no API key). For cloud models, either:

1. Open **http://localhost:3000/settings** after start and save provider / model / key, or  
2. Set env before start, for example:

```bash
# Gemini (OpenAI-compatible endpoint)
ARYX_LLM_PROVIDER=google
ARYX_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
ARYX_LLM_REASON_MODEL=gemini-2.0-flash
ARYX_LLM_API_KEY=your-google-api-key

# Grok (xAI)
ARYX_LLM_PROVIDER=xai
ARYX_LLM_BASE_URL=https://api.x.ai/v1
ARYX_LLM_REASON_MODEL=grok-3
ARYX_LLM_API_KEY=your-xai-key
```

Keys saved in **Settings** stay in API **process memory** (not written to disk). They reset when the API container restarts unless set via env.

---

## 3. Start the stack

```bash
docker compose up -d
```

**First run:** `ollama-init` downloads models (`qwen3.5:0.8b`, `lfm2.5-thinking`, `nomic-embed-text`). Wait until `docker compose ps` shows services healthy and Ollama lists those models.

### Services and ports

| Service | Host URL / port | Role |
|---------|-----------------|------|
| **web** | http://localhost:3000 | Next.js product UI |
| **api** | http://localhost:8088 | FastAPI (`/docs` = OpenAPI) |
| **mcp** | http://localhost:8765/sse | MCP SSE for agents |
| **postgres** | localhost:**55432** → container 5432 | Source of truth (+ pgvector) |
| **falkordb** | localhost:6379 | Graph projection |
| **ollama** | (internal) | Local LLM runtime |
| **worker** | (internal) | Background jobs |

> Host Postgres is on **55432** to avoid clashing with a local Postgres on 5432. Inside Docker, apps still use `postgres:5432`.

There is **no Streamlit service**.

---

## 4. Verify

```bash
docker compose ps
# Expect Up: postgres, falkordb, ollama, api, worker, mcp, web

curl -s http://localhost:8088/health
# {"status":"ok"}  (or similar healthy payload)

curl -o /dev/null -w "%{http_code}\n" http://localhost:3000
# 200

docker compose exec ollama ollama list
# should list pulled models after ollama-init finishes
```

Open:

1. http://localhost:3000 — product UI  
2. http://localhost:3000/settings — confirm LLM provider  
3. Create a **workspace** → **Onboard** (`/start`)

Optional demo data into support tables:

```bash
curl -X POST http://localhost:8088/demo/load \
  -H 'Content-Type: application/json' \
  -d '{"ticket_count":200}'
```

---

## 5. First-time product path

1. **New workspace** (header picker).  
2. **Onboard** — goals → brief → database and/or files → pipeline runs.  
3. **Data → Graph** — interactive entity graph (search, filters, click for detail).  
4. **Ask** — grounded questions with citations.  
5. **Lab** — ontology ON vs OFF (needs populated workspace).

Details: [USER_GUIDE.md](USER_GUIDE.md).

---

## Security checklist (exposed hosts)

If ports are reachable beyond your laptop:

| Action | Why |
|--------|-----|
| Set `ARYX_API_AUTH=required` | Default `optional` allows unauthenticated API use |
| Change `POSTGRES_PASSWORD` / DSN | Defaults are for local demo only |
| Do not publish Postgres/FalkorDB to the public internet | Data stores |
| Prefer a reverse proxy + TLS | Terminate HTTPS in front of 3000/8088 |
| Set `ARYX_LOG_LEVEL=INFO` in production | Compose may use DEBUG on the API for local debugging |

MCP bearer tokens: issue tokens when you leave open “no tokens issued” allow-all behaviour. See architecture/security notes in the codebase (`ARYX_MCP_AUTH_OPTIONAL`).

---

## Entity resolution knobs (optional)

Defaults are tuned for **fast local** runs (LLM adjudication off by default):

```bash
ARYX_ER_AUTO_MERGE=0.92
ARYX_ER_ADJUDICATE=0.90
ARYX_ER_REVIEW=0.75
# Max LLM adjudications per resolve run (0 = off; pairs go to review queue)
ARYX_ER_MAX_ADJUDICATIONS=0
# Skip embedding scoring when match text is shorter than this many chars
ARYX_ER_EMBED_MIN_CHARS=40
ARYX_ER_CHUNK_THRESHOLD=100000
ARYX_PROJECT_DIRTY_MAX=0.30
```

---

## Updating a deployment

```bash
cd aryx
git pull origin main
docker compose build api web worker mcp
docker compose up -d api web worker mcp
```

- **Python/API changes** → rebuild `api` (and `worker` / `mcp` if those images share the same Dockerfile).  
- **Web UI changes** → rebuild `web`.  
- Migrations under the store layer apply **automatically** on API startup (idempotent).

Force clean rebuild if behaviour looks stale:

```bash
docker compose build --no-cache api web
docker compose up -d --force-recreate api web
```

---

## Cloud VM sketch (e.g. EC2)

1. Instance: **4 vCPU / 8 GB RAM / 50 GB+** disk.  
2. Security group: **22**, **3000**, **8088**, **8765** (and 80/443 if proxied). Prefer restrict source IPs.  
3. Clone, `.env` with strong secrets, `docker compose up -d`.  
4. Access via `http://<public-ip>:3000` (or HTTPS via proxy).

Do not rely on shared demo IPs from old docs; use your own host.

---

## Local development (without full Compose UI)

Still need Postgres, FalkorDB, and usually Ollama (Compose those three, or run equivalents).

```bash
# API
python3.13 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ARYX_RDB_DSN=postgresql://aryx:aryx@localhost:55432/aryx
export ARYX_GRAPH_URL=redis://localhost:6379
export ARYX_LLM_BASE_URL=http://localhost:11434
PYTHONPATH=src python -m uvicorn aryx.api.main:app --reload --port 8088

# Web (separate terminal)
cd apps/web
npm install
ARYX_API_URL_INTERNAL=http://localhost:8088 npm run dev
# → http://localhost:3000
```

Smoke tests (no full stack required for pure unit subset):

```bash
PYTHONPATH=src python -m pytest tests/test_ports_seam.py tests/test_grounding.py \
  tests/test_ab.py tests/test_explore.py -q
```

---

## Troubleshooting

### Port already in use

```bash
lsof -ti :3000 | xargs kill -9
lsof -ti :8088 | xargs kill -9
# Postgres host mapping uses 55432
lsof -ti :55432 | xargs kill -9
```

### API unhealthy / migrations

```bash
docker compose logs -f api
```

Migrations run on API startup. Fix DSN/password mismatches in `.env`.

### Web blank or 502

```bash
docker compose logs -f web
docker compose restart web
# Confirm proxy target: ARYX_API_URL_INTERNAL=http://api:8000 inside Compose
```

### Ollama slow or OOM

Reduce parallelism; ensure enough RAM. First model pull is large.

```bash
docker compose logs ollama ollama-init
docker compose exec ollama ollama list
```

### LLM errors in Ask / onboard

1. Check **Settings** → provider, endpoint, model ids.  
2. For Ollama, endpoint from the API container is usually `http://ollama:11434` (not `localhost`).  
3. Restart API after changing env-based keys: `docker compose up -d api`.

### Resolve takes too long

Confirm `ARYX_ER_MAX_ADJUDICATIONS=0` (default). Check match keys are real columns (upload path repairs bad keys). See User guide / Features for ER behaviour.

---

## License

Aryx Lite is **BSL 1.1**. Internal production use is allowed under the Additional Use Grant; competing multi-tenant hosting requires a commercial license. See [LICENSING.md](LICENSING.md) and root [`LICENSE`](../LICENSE).

---

## Next steps

- [User guide](USER_GUIDE.md) — use the product  
- [Features](FEATURES.md) — capability matrix  
- [Architecture](ARCHITECTURE.md) — design  
- [Ingestion guide](INGESTION_GUIDE.md) — deeper ingest detail  
