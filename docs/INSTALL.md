# Installation Guide

## Prerequisites

- **Docker & Docker Compose** — [Install](https://docs.docker.com/compose/install/)
- **Git** — [Install](https://git-scm.com/)
- **Python 3.13** (optional, for local dev without Docker)
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
- **UI** (Streamlit): http://localhost:8501
- **API** (FastAPI): http://localhost:8088 (or http://localhost:8088/docs for OpenAPI)
- **Postgres**: localhost:5432 (user: `aryx`, password from `.env`)
- **FalkorDB**: localhost:6379
- **Ollama**: localhost:11434

### 4. Verify

```bash
docker compose ps
# Should show: postgres, falkordb, ollama, api, ui all "Up"

curl http://localhost:8088/health
# Returns: {"status": "ok"}
```

### 5. First Ingest

1. Open http://localhost:8501 (Streamlit UI)
2. Go to **Ingest tab**
3. Provide context: *"Customer support tickets linked to customers and products"*
4. **Database tab**: Click "Connect & introspect"
   - **RDBMS:** postgresql
   - **Host:** postgres (internal docker network)
   - **Port:** 5432
   - **Database:** aryx
   - **User:** aryx
   - **Password:** (from `.env`)
5. Click **"Connect & introspect"** → agent discovers tables → **Confirm & ingest**

## EC2 Deployment

### Prerequisites

- **EC2 instance** (t3.large+, 4 vCPU, 8GB RAM, 50GB disk)
- **SSH key** (`~/.ssh/aryx-key.pem`)
- **Security group** allows ports 22 (SSH), 80/443 (HTTP/S), 8501 (UI), 8088 (API)

### 1. SSH & Clone

```bash
ssh -i ~/.ssh/aryx-key.pem ec2-user@<instance-ip>
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
docker logs -f aryx-ui-1  # Watch UI startup
```

### 5. Updating a running deployment (git-only flow)

Never `docker run`/`scp` ad-hoc changes. All updates flow through git:

```bash
ssh -i ~/.ssh/aryx-key.pem ec2-user@<instance-ip>
cd /home/ec2-user/aryx
git pull origin main
docker compose build
docker compose up -d
```

If behaviour doesn't match the new code (compose served a stale layer),
force a clean rebuild and verify:

```bash
docker compose build --no-cache
docker compose up -d --force-recreate
docker compose exec api python -c "import aryx.resolution.confidence; print('ok')"
```

Database migrations (`src/aryx/store/migrations/*.sql`, currently 0001-0023)
are idempotent and apply automatically on API startup — no manual step.

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

- **UI:** http://<instance-ip>:8501
- **API:** http://<instance-ip>:8088

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

# Run API
python -m uvicorn src.aryx.api.main:app --reload --port 8088

# Run UI (separate terminal)
streamlit run src/aryx/ui/main.py --server.port=8501
```

(Requires external Postgres + FalkorDB + Ollama. See `docker-compose.yml` for connection strings.)

## Next Steps

- [User Guide](USER_GUIDE.md) — Navigate the UI
- [Ingestion Guide](INGESTION_GUIDE.md) — Detailed ingest workflow
- [Architecture](ARCHITECTURE.md) — System design deep-dive
