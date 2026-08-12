# User Guide — Aryx Lite

Aryx turns the data you already have into a **knowledge graph you can ask questions of**, and ties every answer back to **real source records**.

You do **not** design a full schema up front. You state goals in plain English, point Aryx at databases or files, approve the model it proposes, and explore.

Everything lives in **workspaces** — isolated projects (partitions + graph). Use one workspace per use case (e.g. Support, Sales, BoM).

---

## Open the app

| Environment | URL |
|-------------|-----|
| Local (Docker) | http://localhost:3000 |
| Your server | http://\<host\>:3000 |

**Only UI:** Next.js. There is no Streamlit interface.

| Need | Where |
|------|--------|
| Install / ports / env | [INSTALL.md](INSTALL.md) |
| LLM keys / provider | **Settings** → `/settings` |
| API docs | http://localhost:8088/docs |

---

## Top navigation

| Control | Purpose |
|---------|---------|
| **Home** | Workspaces, model gate, create / open / reset / delete |
| **Brief** | Grounding questions — usually drafted after data load; edit anytime |
| **Data** | Explorer (Tree / Table / Graph) + **Correct data** coach |
| **Model** | Ontology canvas (types & relationships; seeded from smart plan) |
| **Lab** | Accuracy Lab (ontology ON vs OFF) |
| **Ask** | Grounded Q&A with citations |
| **MCP** | Connect Claude / coding tools / agents to Aryx (`/mcp`) |
| **Observe** | Jobs, workspace vitals, storage truth |
| **Settings** | LLM provider, models, API key (powers smart understand + Ask) |
| **Jobs** chip | Live ingest progress |
| **Questions** bell | Human-in-the-loop ingest queue |
| **Workspace** picker | Switch, create, or delete (non-Default) workspaces |

**Setup** (`/start`): data first → smart review → build. Opens automatically for empty workspaces. See [UI_BUSINESS_FLOW.html](UI_BUSINESS_FLOW.html).

---

## 1. Workspaces

1. **Home** lists every workspace with entity counts and Brief status.  
2. Open the **workspace pill** (top right) to switch or create.  
3. **New workspace** — name + optional description → guided setup.  
4. **Reset & re-ingest** — clears data for that workspace but keeps brief, types, and corrections.  
5. **Delete** (non-Default only) — permanent removal; requires checkbox + typing `DELETE`. The **Default** workspace (id 1) cannot be deleted.

Each workspace has its own partitions and graph. Prefer **one workspace per project**.

---

## 2. Brief (`/brief`)

Ground extraction with domain, aim, objectives, scope, roles, and proof questions.

- **Primary:** type answers directly; all fields optional; **Save Brief**.
- **Optional AI draft:** collapse/expand section — documents are read for drafting only (not graph ingest; not retained as files after the session).
- Overwriting with AI when fields are filled asks for confirmation.

---

## 3. Settings (`/settings`) — models & keys

Controls the **LLM engine** used for Ask, discovery, and related stages.

| Field | Notes |
|-------|--------|
| **Provider** | Local (Ollama), Claude (Anthropic), OpenAI / compatible, Gemini, Grok (xAI) |
| **Fast model** | Lighter tasks (e.g. term extraction) |
| **Answer model** | Main reasoning / answers |
| **Endpoint** | Base URL (Ollama inside Docker: `http://ollama:11434`) |
| **API key** | Required for cloud providers; leave blank for local Ollama |

**Save** applies **live** (no restart). Keys are held in API process memory and are **not** written to git. Restarting the API clears UI-saved keys unless set in `.env` (see [INSTALL.md](INSTALL.md)).

---

## 4. Setup wizard (`/start`)

Progress steps along the top; you can leave and return.

**Product rule: data first.** You load files or connect a database **before**
filling a blank brief. Aryx (your Settings model — Gemini, Ollama, etc.) reads
samples, drafts the brief and a graph plan, then asks only for light corrections
and optional extra documents.

### Step 1 — Sources

Choose **Database**, **Files**, and/or **Types only** (skip data for now).

### Step 2 — Load data

Connect a DB or upload CSV/JSON/PDF/Word/images. Aryx samples the content.

### Step 3 — Smart review

The model proposes:

- What the data is  
- A full **brief** (domain, aim, objectives, scope, roles, proof questions)  
- A **graph plan** (entity types, relationships, column dimensions)  
- Optional follow-up questions and **suggested extra documents**

Edit anything that looks wrong. Add more files if suggested. Then confirm.

### Step 4 — Build

Brief is saved; ingest runs steered by that brief + plan. Explore on **Data**
and **Model**, then **Ask**.

### Brief page (`/brief`)

Still available anytime to edit the brief. Prefer letting smart review draft it
after you load data; hand-filling six empty fields first is no longer the main path.

### Database notes

Fill host, database, user, password (Advanced: port, dialect, schema). **Connect** runs a **read-only** test. Passwords are encrypted before storage. Inside Compose, host for the bundled DB is often `postgres` (not `localhost`).

### Files notes

Drag-and-drop or browse (typically up to 50 files / 20 MB each / 50 MB total). Smart review samples headers and rows before full ingest. Multi-file batches get per-file types; cross-file FK links can be inferred after land.

### Pipeline

Live progress on the wizard and in the **Jobs** chip. HITL questions appear in the **Questions** bell when needed.

When the job completes, a **result card** appears inline with three sections — each has its own **Refresh** button:

| Block | What it shows | Source |
|-------|--------------|--------|
| Records processed | How many source rows were read | Job event log |
| What we discovered | Entity types found + deduplication count | `/data/summary` |
| Connections mapped | Total relationships in the graph | `/admin/workspace-overview` |

A collapsed **"Diagnose this run"** section shows the full event log (stage, time, detail) on demand — useful for spotting slow stages or warnings.

### Step 6 — Done

Summary tiles of types and counts (auto-refresh while jobs finish). Jump to **Ask** or **Model**.

---

## 4. Ask (`/`) — question your graph

1. Type a question (or use a starter chip).  
2. Answer streams with **citation / provenance** when grounded.  
3. Use follow-up chips to dig deeper.

**Tips**

- Name a **type or entity** (*“Tell me about Customer NetOps Atlantic”*) for tighter grounding.  
- Empty workspaces disable Ask until you onboard data.

---

## 5. Data (`/data`) — transparency explorer

See **what was resolved** and **where it came from**.

**Summary strip:** entity counts by type, sources, and a **dedup story**  
(*N source records → M entities, K duplicates merged*).

### Tree lens

**Types → entities → attributes**, with provenance chips  
(`system.dataset#record_id`) on contributing sources.

### Table lens

Per-type grid; sort by headers; row click opens a **provenance drawer** and selects the entity for **Correct data**. **Show more** pages rows.

### Graph lens (entity-level)

Interactive **entity** graph (not only type bubbles):

| Action | Result |
|--------|--------|
| Pan / zoom / minimap | Navigate large graphs |
| Drag nodes | Rearrange for reading |
| Fullscreen | Focused exploration |
| **Search** | Find an entity by name and focus the camera |
| **Type chips** | Toggle types on/off to declutter |
| **Click a node** | Highlight neighbours; detail panel; select for **Correct data** |
| Detail panel | Type, attributes, source records, relationships; click a related entity to walk the graph |
| Large graphs | Hub-and-spoke **cluster layout** for readability |

If relationships are missing, upload multi-file data with shared keys or define relationships on **Model**.

### Correct data (coach)

Floating control bottom-right on **Data** (and Model):

1. Select an entity (Table row or Graph node).  
2. Open **Correct data** — choose an intent (Wrong type, Merge, Link, …) or type a fix.  
3. Aryx **proposes**; click **Apply** only when correct.  
4. **Standing rules** tab lists corrections replayed on future ingest.

Use **Ask** for questions about the graph — not Correct data.

---

## 6. Model (`/model`) — ontology canvas

Visual model of **entity types** and **relationships**.

- **Nodes** — attributes, instance counts, status (**proposed** vs **approved**).  
- **Edges** — named relationships / inheritance.  
- **Toolbar** — re-layout, refresh, **New type**.

**Inspector** (click a type):

- Approve proposed types  
- Attributes (+ AI suggest)  
- **Survivorship** — how conflicting values win on merge  
- Axioms / rules  
- Delete type (confirm)

Drag between type handles to **add a relationship**. Click an edge to remove it.

---

## 7. Lab (`/lab`) — Accuracy Lab

Answers: **does the ontology make answers better?**

Same question, same model, two modes:

- **Ontology ON** — grounded in your graph + citations  
- **Ontology OFF** — no graph grounding  

Plus a **reasoner-check** (structural constraints the LLM cannot fake). Needs a **populated** workspace; empty workspaces show an empty state.

---

## Human-in-the-loop (Questions)

When ingest or resolution needs a human decision, Aryx **queues a question** instead of guessing.

1. Open the **bell** in the header.  
2. Read the prompt; pick a suggestion or type an answer.  
3. **Answer** to unblock the pipeline.

Also used for ambiguous entity-resolution pairs in the review band.

---

## Entity resolution & survivorship (what you feel in the product)

After ingest, Aryx:

1. Blocks candidate duplicates by keys  
2. Scores pairs  
3. Auto-merges strong matches, queues mid-band for review, rejects weak ones  
4. Builds a **golden record** per cluster  

Defaults favour **speed on local models** (LLM adjudication can be limited via env — see [INSTALL.md](INSTALL.md)).  

**Survivorship** (Model → Inspector → Survivorship) controls which source wins when attributes disagree (default strategy + per-attribute overrides).

---

## Practical tips

- **State goals in plain English** — nouns become model seeds.  
- **Name entities in Ask** — better grounding.  
- **Trust the chain** — use Data provenance for anything important.  
- **Approve types** on Model before treating them as final.  
- **One workspace per project.**  
- **Use Lab** when someone asks if the AI is inventing answers.  
- **Configure Settings** before blaming “LLM unavailable” errors.

---

## Related docs

- [Install](INSTALL.md) — Docker, env, security, updates  
- [Features](FEATURES.md) — full capability list  
- [Architecture](ARCHITECTURE.md) — how it works  
- [Ingestion guide](INGESTION_GUIDE.md) — deeper ingest  
- [Licensing](LICENSING.md) — BSL summary  
