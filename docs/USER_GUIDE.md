# User Guide

## Overview

Aryx is built around **workspaces** — isolated projects with their own data, graph, and LLM settings. Start with the default workspace or create new ones for different use cases (Customer Support, Sales, BoM).

## Main Navigation

Open http://localhost:8501 and you'll see the sidebar:

- **🏠 Home** — Overview of active workspace, quick stats
- **📥 Ingest** — Add data from databases or documents
- **💬 Ask** — Query the knowledge graph in natural language
- **📊 Graph** — Interactive visualization; drill-down to entity details
- **📊 Observability** — Job history, LLM tokens/latency, graph stats
- **⚙️ Settings** — Switch workspace, configure LLM provider (Local/Claude/OpenAI)

## Workspace Management

### Switch or Create Workspace

1. **Sidebar:** Click workspace dropdown (top left)
2. **Manage workspaces** button
3. **New workspace** — type name, click "Create"
4. **Delete** button removes workspace + all data (instant physical purge)

**Tip:** One workspace per project to keep data isolated. Default workspace is protected (can't delete).

## Ingestion Workflow

### Database Path

1. Go to **Ingest tab** → **Database (auto-discover)** tab
2. **Step 1 — What are you building?**
   - Provide crisp context (e.g., *"Customer accounts Q2 2026: include names, company, industry, deal size"*)
   - Or upload a context file (TXT/PDF/DOCX with entity description)
3. **Step 2 — Connect**
   - Fill RDBMS (postgresql, mysql, etc.), host, port, database, user, password
   - Click **"Connect & introspect"** — system reads table schema
4. **Step 3 — Auto-discover**
   - Agent maps tables to entity types using your context
   - Click **"🤖 Run discovery agent"**
3. **Step 4 — Review & ingest**
   - Edit proposed entity types / match keys as needed
   - Click **"Ingest selected tables"** → job starts
   - Watch progress in **Ingestion progress** panel below

### Document Path

1. Go to **Ingest tab** → **Documents (folder)** tab
2. **Step 1 — What are you building?**
   - Provide context (text or upload file: TXT/PDF/DOCX)
   - Without context, discovery fails (system requires understanding)
3. **Step 2 — Documents**
   - Drop files (JSON, CSV, PDF, PPTX, DOCX, images)
   - Max 50 files, 2 MB each
   - Click **"Read & discover"** → system extracts text, finds entities
4. **Review results**
   - Tick entity types to keep
   - Click **"Confirm & add to graph"** → job starts
   - Use **🔄 Reset** to retry with different context/files

## Querying the Graph

### Ask Tab

1. Go to **Ask tab**
2. Type a natural-language question:
   - *"Which customers are associated with product X?"*
   - *"Find all support tickets from acme.com"*
   - *"Show me high-value deals closed in the last 30 days"*
3. **Chat history** appears on left; responses on right
4. Each response shows:
   - **Answer** — LLM reasoning + facts
   - **Sources** — which records (with links to Graph tab)
   - **Token count & latency** — cost/speed of the query

**Tip:** Ask follows conversation context — reference earlier messages ("What about the accounts I just mentioned?").

## Graph Exploration

### Interactive Canvas

1. Go to **Graph tab**
2. **Search** — find entities by name, type, or property
3. **Type filter** — show only Person, Company, Product, etc.
4. **Hide isolated nodes** — clean up nodes with no relationships
5. **Click node** → **Drill-down panel** opens:
   - Entity name, type, properties
   - Related entities (neighbors)
   - **Provenance** — which source records created this entity
   - **PATH** — shortest graph path to another entity

### Path Queries

Click an entity → panel shows "Path to..." button:
1. Start: *Entity A*
2. End: Click "Path to..." → select *Entity B*
3. Returns shortest path (e.g., Person → Company → Product)

## Settings

### LLM Provider

1. Go to **Settings tab**
2. **Active provider** dropdown:
   - **Local** — Uses on-box Ollama models (free, slow ~10–60s)
   - **Claude (Anthropic)** — Paste API key; instant, quality
   - **OpenAI** — Paste API key; instant
   - **Gemini** — Paste API key; instant
3. Paste key (if not Local) → click **"Set & test"**
4. **Change takes effect immediately** for future queries

### Workspace Context

Shows summary of current workspace:
- Entities & relationships count
- Recent ingestion jobs
- Graph build date

## Observability

### Jobs & Runs

**Observability tab:**
- **Job list** — ingestion jobs, status, progress, timeline
- **LLM tokens** — cumulative tokens used (cost tracking)
- **Graph stats** — node count, edge count, rebuild timestamp

Useful for auditing what ran when and how much LLM you've used.

## Tips & Tricks

- **Context is critical** — "Customer data" won't work; "Customer accounts Q2: names, company, deal amount" will
- **Reset after failure** — Documents tab has 🔄 reset button to retry with better context/files
- **Provenance** — Every entity shows which source records created it; trust the chain
- **Sources matter** — Ask provides links to exact records; click to verify
- **Workspace per project** — Customers vs. Sales vs. Products deserve separate graphs
- **Local + Cloud hybrid** — Use Ollama for cheap stages; pay for Claude on hard decisions only (configured in Settings)

## Next Steps

- [Ingestion Guide](INGESTION_GUIDE.md) — Detailed walkthrough of ingest pipeline
- [Architecture](ARCHITECTURE.md) — How Aryx works under the hood
