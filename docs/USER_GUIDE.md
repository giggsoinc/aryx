# User Guide

## Overview

Aryx turns the data you already have into a **knowledge graph you can ask questions of** — and proves every answer against the real source records it came from. Where most tools make you design a schema up front, Aryx is discovery-driven: you state what you want to figure out in plain English, point it at your data, and it proposes the model for you to approve.

Everything is organised around **workspaces** — fully isolated projects, each with its own data partitions and graph. Use one per use case (Customer Support, Sales Pipeline, BoM), and nothing leaks between them.

This guide walks through the **Next.js web UI**, the primary interface. Open it at:

- **Local:** http://localhost:3000
- **Live box:** http://3.91.73.197:3000

The top nav has five surfaces — **Ask**, **Model**, **Data**, **Lab**, **Onboard** — plus a workspace picker on the right. A new, empty workspace drops you straight into Onboard.

> **UI:** Next.js on port 3000 is the only product UI. Configure LLM providers under **Settings** (`/settings`).

---

## The Top Nav

Across the top of every page you'll find:

- **Logo** (left) — returns to Ask.
- **Ask** · **Model** · **Data** · **Lab** · **Onboard** — the five surfaces.
- **Jobs chip** — a live spinner appears here while any ingest job is running; click it for per-job status.
- **Questions bell** — appears when the workspace has pending human-in-the-loop questions (hidden during the Onboard wizard and on empty workspaces).
- **Workspace picker** (right) — switch or create workspaces.

---

## 1. Workspaces (Picker, Top-Right)

The pill on the top right shows your active workspace. Click it to drop down a panel:

1. **Switch** — pick any workspace in the list; the dot marks the active one. Switching reloads every surface against that workspace's isolated data and graph. (If you switch while inside the Onboard wizard, Aryx routes you to Ask so you're not stranded mid-setup.)
2. **New workspace…** — the dropdown morphs into an inline form (no modal). Give it a **Name** (e.g. *Sales Pipeline*) and an optional one-line description of what it's for, then **Create & open setup**.

Creating a workspace routes you straight into the **Onboard** wizard, because a fresh workspace has its own empty partitions and graph and needs data before anything else works.

> Each workspace is fully isolated — its own partitions, its own graph. One workspace per project keeps data clean.

---

## 2. Onboard (`/start`) — Guided Setup

Onboard is a step-by-step wizard that takes you from "I have some data" to "I can ask questions of it." Progress shows along the top; you can leave and come back.

### Step 1 — Your goals

> *"What do you want Aryx to help you figure out?"*

List 2–5 questions or goals in plain English — *"Find customers at risk of churning," "See where my BoM has single-source risk."* Starter chips are there to adapt. The **nouns in your goals become the first kinds of records** Aryx looks for, and the goals themselves become the test of whether the model works. (You can **Skip** and do this later.)

### Step 2 — Confirm the brief

Aryx reads your goals back as a short brief:

- **You track** — the domain
- **You want** — the aim
- **In scope** — the candidate kinds of records (shown as chips)

If it's right, **Looks right — keep going**. If not, hit **Let me edit**, adjust any field inline, and save. Anything unexpected later gets flagged for your review — nothing happens silently.

### Step 3 — Pick your sources

Tick any that apply (you can mix them):

- **Database** — Postgres, MySQL, Oracle, and more
- **Files** — PDF, CSV, Word, Excel, slides, JSON, images
- **Add by hand** — informational here; you create types manually on the **Model** canvas

The wizard loops through every source you pick — Database first, then Files.

### Step 4a — Connect a database

The connection form is driven by the database type. Supported dialects include **postgres / postgresql**, **mysql / mariadb**, **oracle**, and a generic **rest** source.

Fill in host, database, user, password (and an **Advanced** disclosure for port, dialect, schema, extra context). Click **Connect**:

- Aryx opens a **read-only** test connection and lists your tables.
- Your **password is encrypted before it touches disk** with a server-only key, and the UI never shows it again.
- If the test fails, you see the error inline and can fix it.

### Step 4b — Upload files

Drag files onto the drop zone or click to browse. Accepted: **PDF · DOCX · PPTX · CSV · JSON · images** (plus TXT/MD). Limits today: up to **50 files, 2 MB each, 50 MB total**. Oversize files are flagged in red. Click **Upload & continue**.

Behind the scenes each document is **chunked → PII-screened → embedded for semantic search → entities extracted** into your graph.

### Step 5 — Pipeline runs (live)

The pipeline runs with live progress. You can watch it here, or via the **Jobs chip** in the header. If Aryx hits a decision only a human should make, it **pauses and asks** — answer in the Questions drawer (see *Human-in-the-loop* below) to unblock it.

### Step 6 — Done

> *"Here's what I learned:"*

Tiles show each kind of record Aryx found and how many of each, plus total records and connections. This screen **auto-refreshes** while ingest jobs are still running, so counts catch up as records land. From here jump to **Ask Aryx a question** or **See the map** (Model).

---

## 3. Ask (`/`) — Question Your Graph

Ask is natural-language Q&A grounded in the workspace's resolved entities. Every answer is backed by the real records behind it.

1. Type a question in the composer (⌘K focuses it), or click a **starter chip**.
2. The answer streams in. **Provenance/citation pills** appear beneath it, tracing the answer back to source entities.
3. **Follow-up chips** let you keep the thread going — *"What else do we know about that Customer?", "Show me the underlying records."*

**What grounds best:**

- **Entity-specific questions** — naming a specific kind of record or a specific entity (*"Tell me about the Customer NetOps Atlantic," "Which Agents have resolved the most Tickets?"*) ground tightly, because Aryx can lock onto a concrete noun.
- **Generic / meta questions** — broad questions answer from a **workspace overview** rather than a specific entity.

If the active workspace is empty, the composer is disabled and prompts you to onboard data first.

---

## 4. Data (`/data`) — The Transparency Explorer

Data is where you see **everything Aryx resolved** — what type each thing is and the exact source record it traces to. Nothing hidden in a database you can't see.

At the top, a **summary strip** shows:

- **Entities · types** — total count and a coloured tile per type with its count.
- **Sources** — each source with a bar and its record count.
- **The dedup story** — e.g. *"5,000 source records → 3,200 entities (1,800 duplicates merged)."*

Below that, three lenses:

### Tree lens

Expandable hierarchy: **types → entities → attributes**. Expand a type to page through its entities; expand an entity to see its attributes plus the **provenance chips** (`system.dataset#record_id`) for every source record that contributed to it.

### Table lens

Pick a type from the left rail to get a **per-type records grid**. Columns are the most common attributes; **click any header to sort**. **Click a row** to open a **provenance drawer** showing the entity's attributes and a numbered trace of every source record (`system.dataset#record_id`) it was built from. Page in more rows with **Show more**.

### Graph lens

A **type-level knowledge map**: one node per type, **sized by entity count**, with edges **labelled by relationship name and count**. It stays legible at any scale. If entities exist but no relationships are defined yet, the map shows the types and tells you to connect them with foreign-key links.

---

## 5. Model (`/model`) — The Ontology Canvas

Model is the visual ontology: the entity types Aryx found and how they relate. It's an interactive canvas (drag, zoom, mini-map, re-layout).

- **Nodes** are entity types, each showing its attributes, instance count, and status (**proposed** vs **approved**).
- **Edges** are relationships — `subClassOf` for inheritance, named relationship types between types.
- **Toolbar** — re-layout, refresh, and **New type**, with live type/relationship counts.

**Click a type** to open the right-hand **Inspector**:

- **Approve this type** — proposed types (discovered during ingest) pass through an approval gate before they're active.
- **Attributes** tab — view/edit attributes, with an **AI: suggest attributes** button that proposes attribute names (with a rationale) as chips you accept one at a time.
- **Survivorship** tab — set how duplicate records merge into the golden record (default strategy plus per-attribute overrides; see *Entity resolution* below).
- **Axioms** tab — structural constraints (e.g. disjoint, cardinality) the reasoner enforces.
- **Rules** tab — inference rules (`when <attribute> <op> <value> → <action>`).
- **Delete this type** — type-and-confirm deletion (records stay in the graph but are no longer schema-registered).

**Add relationships** by dragging from one type's handle to another — Aryx prompts for a snake_case name (e.g. `opened_by`) and persists it. **Click an edge** to delete a declared relationship.

If the workspace has no types yet, an empty state points you back to guided setup or lets you add records by hand.

---

## 6. Lab (`/lab`) — The Accuracy Lab

The Lab answers one question: **does the ontology actually make answers more accurate?**

You ask a question, and Aryx runs the **same model twice**:

- **Ontology ON** — grounded in your knowledge graph, with citations to real source records.
- **Ontology OFF** — no grounding; the model answering from its own parameters alone.

> **Needs a workspace with data.** On an empty workspace the Lab shows an empty-state pointing you to onboard or switch workspaces — it has nothing to contrast otherwise. On a populated workspace, **example questions are generated from real entities** in that workspace, so a click actually grounds.

Results:

- **Scorecard** — four metrics, on vs off: **Grounded** (yes/no), **Citations**, **Source records**, **Evidence used**.
- **Two variant cards** — the ON answer with its citations (each citation naming the entity, its type, and the `system.dataset#record_id`) and an evidence-coverage bar; the OFF answer marked ungrounded, with nothing traceable.
- **Reasoner-check card** — a third proof dimension the LLM can't fake: how many axioms are enforced across how many entities, and how many contradictions the reasoner would **block** that a text-only answer would let through. (If no axioms are defined, it nudges you to add some in Model.)

---

## Human-in-the-Loop (Questions Drawer)

When ingest needs a human call, Aryx **pauses and queues a question** instead of guessing. The **Questions bell** in the header lights up with a count.

Open the drawer to:

1. Read each pending question (tagged by kind).
2. Pick from suggested options, or type your own answer — the **AI suggestion** pre-fills when there is one.
3. **Answer** to unblock the pipeline.

When the queue is empty, the drawer reads *"All caught up."*

---

## Entity Resolution & Survivorship

After ingest, Aryx resolves duplicates automatically so each real-world thing is **one** entity:

- It blocks records by shared keys, scores candidate pairs, and merges the confident ones — auto-merging strong matches, routing borderline pairs for review (these surface as questions), and rejecting weak ones.
- Merged clusters collapse into a single **golden record**.
- The **dedup story** on the Data tab (*N source records → M entities, K duplicates merged*) is the visible result.

**Survivorship policy** (Model → Inspector → Survivorship) controls *which* value wins when sources disagree on an attribute. Set a default strategy and override per attribute — for example, let `revenue` take the most-recent value while everything else follows source priority.

---

## Practical Tips

- **State goals in plain English.** The nouns become your model — *"Match support tickets to the right expert agent"* gives Aryx `tickets` and `agents` to find.
- **Name entities when you ask.** *"Tell me about the Customer NetOps Atlantic"* grounds far better than *"tell me about customers."*
- **Trust the chain.** Every entity, every answer, every Lab citation traces to a `system.dataset#record_id`. Use the Data tab's provenance drawer to verify anything.
- **Approve, don't assume.** Proposed types and relationships wait for your nod in Model before they're active.
- **One workspace per project.** Customers, Sales, and Products deserve separate, isolated graphs.
- **The Lab is your proof.** When someone asks "is the AI just making this up?", run the same question on/off and show them the scorecard.

---

## Next Steps

- [Install Guide](INSTALL.md) — Get running locally or on EC2
- [Feature Matrix](FEATURES.md) — All capabilities at a glance
- [Architecture](ARCHITECTURE.md) — How Aryx works under the hood
- [Ingestion Guide](INGESTION_GUIDE.md) — Detailed ingest walkthrough
