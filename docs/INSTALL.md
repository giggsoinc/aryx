# Installation Guide

## Prerequisites

- **Docker & Docker Compose** — [Install](https://docs.docker.com/compose/install/)
- **Git** — [Install](https://git-scm.com/)
- **Python 3.11** (optional, for local dev without Docker)
- **Node 20+** (optional, only to run the Next.js web UI outside Docker)
- **Ollama** (optional, for local LLM models; included in docker-compose)

## Local Setup (Docker Compose)

### 1. Clone & Navigate

```bash
git clone https://github.com/giggsoinc/aryx.git
cd aryx
```

### 2. Configure Environment

Copy `.env.example` to `.env` (if provided), or set defaults:

```bash
# .env (or set via shell)
export POSTGRES_PASSWORD=aryx_dev_password
export POSTGRES_DB=aryx
export OLLAMA_NUM_PARALLEL=1
```

### 3. Start Services

```bash
docker compose up -d
```

**Services:**
- **Web UI** (Next.js — primary): http://localhost:3000
- **API** (FastAPI): http://localhost:8088 (or http://localhost:8088/docs for OpenAPI)
- **MCP** (SSE, for AI agents): http://localhost:8765/sse
- **UI** (Streamlit — legacy): http://localhost:8501
- **Postgres**: localhost:5432 (user: `aryx`, password from `.env`)
- **FalkorDB**: localhost:6379
- **Ollama**: localhost:11434

### 4. Verify

```bash
docker compose ps
# Should show: postgres, falkordb, ollama, api, worker, mcp, ui, web — all "Up"

curl http://localhost:8088/health   # API → {"status": "ok"}
curl -o /dev/null -w "%{http_code}\n" http://localhost:3000   # web → 200
```

### 5. First Ingest (the /start wizard)

The primary onboarding flow is the **guided wizard** in the web UI:

1. Open http://localhost:3000 → top-right workspace picker → **New workspace**
2. You land on **`/start`**:
   - **Goals** — describe what you're tracking and your objectives;
     Aryx drafts a brief from it (edit/confirm)
   - **Sources** — add a data source:
     - **Database** (`postgres`/`postgresql`/`mysql`/`mariadb`/`oracle`/`rest`):
       host `postgres`, port `5432`, db `aryx`, user `aryx`, password from `.env`
       (or any external DB), or
     - **Files** — upload CSV / PDF / DOCX / PPTX / JSON
   - **Run** — the pipeline discovers schema → resolves entities → projects the
     graph; watch live progress, then land on **Done**
3. Explore the result in **Ask**, **Data**, **Model**, and **Lab**.

> Optional demo data: `curl -X POST localhost:8088/demo/load -H 'Content-Type: application/json' -d '{"ticket_count":200}'`
> loads synthetic radio-equipment support data into the source tables.

## EC2 Deployment

### Prerequisites

- **EC2 instance** (t3.large+, 4 vCPU, 8GB RAM, 50GB disk)
- **SSH key** (e.g. `~/.ssh/rvdts-oracle-key.pem`)
- **Security group** inbound: 22 (SSH), **3000 (web UI)**, 8088 (API),
  **8765 (MCP)**, optionally 8501 (legacy Streamlit), 80/443 if behind a proxy

> Current deployment: `ec2-user@ec2-3-91-73-197.compute-1.amazonaws.com`,
> app dir `/home/ec2-user/aryx`, tracks branch `main`.

### 1. SSH & Clone

```bash
ssh -i ~/.ssh/rvdts-oracle-key.pem ec2-user@<instance-ip>
cd /home/ec2-user
git clone https://github.com/giggsoinc/aryx.git
cd aryx
```

### 2. Create `.env`

```bash
cat > .env <<'EOF'
POSTGRES_PASSWORD=production_secret_here
POSTGRES_DB=aryx
OLLAMA_NUM_PARALLEL=1
ARYX_LOG_LEVEL=INFO
EOF
```

### 3. Start

```bash
docker compose build --no-cache
docker compose up -d
```

### 4. Verify

```bash
docker compose ps
docker logs -f aryx-web-1   # watch the Next.js web UI start
docker logs -f aryx-api-1   # watch the API + migrations
```

### 5. Updating a running deployment (git-only flow)

Never `docker run`/`scp` ad-hoc changes. All updates flow through git:

```bash
ssh -i ~/.ssh/rvdts-oracle-key.pem ec2-user@<instance-ip>
cd /home/ec2-user/aryx
git pull origin main
# Rebuild what changed: api/worker/mcp/ui share the Python image; web is the
# Next.js app. Python changes -> rebuild api (and worker/mcp/ui); UI changes -> web.
docker compose build api web
docker compose up -d api web
```

If behaviour doesn't match the new code (compose served a stale layer),
force a clean rebuild and verify the file is actually in the image:

```bash
docker compose build --no-cache api web
docker compose up -d --force-recreate api web
docker compose exec api test -f /app/src/aryx/ports/container.py && echo ok
```

Database migrations (`src/aryx/store/migrations/*.sql`, currently 27) are
idempotent and apply automatically on API startup — no manual step.

### 6. Tuning (optional .env keys)

```bash
# REST auth: off | optional (default) | required
ARYX_API_AUTH=optional
# ER funnel thresholds (defaults from the G9 measured sweep)
ARYX_ER_AUTO_MERGE=0.92
ARYX_ER_ADJUDICATE=0.90
ARYX_ER_REVIEW=0.75
# Chunked resolution kicks in above this record count
ARYX_ER_CHUNK_THRESHOLD=100000
# Incremental projection when dirty-set below this fraction
ARYX_PROJECT_DIRTY_MAX=0.30
```

### 7. Access

- **Web UI:** http://<instance-ip>:3000  (primary)
- **API:** http://<instance-ip>:8088  (`/docs` for OpenAPI)
- **MCP (SSE):** http://<instance-ip>:8765/sse
- **Streamlit (legacy):** http://<instance-ip>:8501

## Troubleshooting

### Port Already in Use

```bash
# Kill process on port 8501
lsof -ti :8501 | xargs kill -9

# Or use different port in docker-compose override
```

### Postgres Connection Refused

```bash
# Check if postgres is healthy
docker compose exec postgres pg_isready -U aryx

# View logs
docker logs aryx-postgres-1
```

### Ollama Models Slow / Out of Memory

Edit `docker-compose.yml`:
```yaml
ollama:
  environment:
    - OLLAMA_NUM_PARALLEL=1  # Reduce parallel model loads
    - OLLAMA_MAX_VRAM=4gb    # Cap VRAM usage
```

Rebuild: `docker compose up -d ollama`

### UI Won't Load / Blank Page

```bash
# Restart UI container
docker compose restart ui

# Check logs
docker logs -f aryx-ui-1
```

## Development (Without Docker)

```bash
# Create venv
python3.13 -m venv venv
source venv/bin/activate

# Install deps
pip install -r requirements.txt

# Run API (PYTHONPATH=src so `aryx` is importable)
PYTHONPATH=src python -m uvicorn aryx.api.main:app --reload --port 8088

# Run the Next.js web UI (separate terminal)
cd apps/web && npm install && \
  ARYX_API_URL_INTERNAL=http://localhost:8088 npm run dev   # → http://localhost:3000

# Or the legacy Streamlit UI
streamlit run src/aryx/ui/main.py --server.port=8501
```

(Requires external Postgres + FalkorDB + Ollama. See `docker-compose.yml` for connection strings.)

Run the test suite (no Docker needed for the pure-logic subset):

```bash
PYTHONPATH=src python -m pytest tests/test_ports_seam.py tests/test_grounding.py \
  tests/test_ab.py tests/test_explore.py -q
```

## Verification Checklist

After starting services, verify everything is healthy:

```bash
# 1. All containers running
docker compose ps
# Expect: postgres, falkordb, ollama, api, worker, mcp, ui, web — all "Up"

# 2. API health
curl http://localhost:8088/health        # {"status": "ok"}

# 3. Web UI loads
curl -o /dev/null -w "%{http_code}\n" http://localhost:3000   # 200

# 4. Platform / edition (Phase 0 ports seam)
curl -s "http://localhost:8088/admin/observability?workspace_id=1" | grep -o '"edition":"[a-z-]*"'

# 5. Ollama model available
docker compose exec ollama ollama list    # should show nomic-embed-text

# 6. FalkorDB reachable (FalkorStore needs a url + graph name)
docker compose exec api python -c "
from aryx.graph.falkor_store import FalkorStore
from aryx.config import get_settings
FalkorStore(get_settings().graph_url, 'aryx_ws_1'); print('FalkorDB: ok')"

# 7. Open http://localhost:3000 — pick a workspace, land on /start or Ask
```

## Next Steps

- [User Guide](USER_GUIDE.md) — Navigate the UI, adjudication queue, actions
- [Feature Matrix](FEATURES.md) — All capabilities at a glance
- [Ingestion Guide](INGESTION_GUIDE.md) — Detailed ingest workflow
- [Architecture](ARCHITECTURE.md) — System design deep-dive
