# Aryx Lite — Business & Leadership Guide

**Audience:** Product owners, operations leads, support/sales ops, data/analytics leaders, CTO/CIO/CDO technical sponsors  
**Edition:** Aryx Lite (self-hostable product in this repository)  
**Version:** 1.7.x

---

## What is Aryx Lite?

**Aryx** is the **self-building context layer for AI agents**.

In plain language: you connect the data your company already has. Aryx figures out **what the things are**, **when two records are the same real-world thing**, and **how things link**. It keeps that map available so AI assistants and applications answer from **connected business context**, not disconnected files and spreadsheets.

**Aryx Lite** is the version you can run yourself (laptop, VM, or small server) to prove value quickly—without waiting for a multi-year “enterprise ontology program.”

| What you get | What you do not need on day one |
|--------------|----------------------------------|
| Connected view of customers, tickets, products, etc. | A team of ontologists drafting every class by hand |
| AI answers with sources you can check | Blind chat over random PDFs |
| One workspace per initiative | Replacing your CRM/ERP |
| Clear path from data → understanding → AI | Buying a separate “vector DB project” first |

**Tagline for sponsors:**

> **Retrieval finds information. Aryx connects meaning.**

---

## Why it is critical (business point of view)

### The business problem

AI pilots are easy to demo and hard to trust in production because:

1. **Customer 360 is a slogan** — the same customer is named differently in CRM, billing, and support.  
2. **Agents sound confident and are wrong** — they invent links between systems.  
3. **Support and ops waste time** — people manually stitch Salesforce + ERP + tickets + email.  
4. **Compliance and risk** — “the AI said so” is not enough; you need **where the fact came from**.  
5. **Every new AI use case restarts** — support bot, sales assistant, and risk tool each rebuild the same context.

### Why this is not “just another chatbot project”

| Approach | What it optimizes | What it misses |
|----------|-------------------|----------------|
| Classic search / RAG | Finding documents | Business relationships |
| Bigger LLM only | Fluent language | Stable identity across systems |
| Point tools per team | Local productivity | Shared, durable company context |
| **Aryx Lite** | **Connected, grounded context** | Does not replace systems of record |

### Business outcomes that matter

- **Faster, safer AI answers** for support, ops, and knowledge work.  
- **Less rework** building “who is who” into every prompt and bot.  
- **Auditability** — facts can be traced to source records.  
- **Reusable context** — one workspace graph, many agents and apps.  
- **Faster time-to-value** than multi-year semantic modeling programs.

### When Aryx Lite is the right first step

- You have **multiple sources** that talk about the same people, accounts, products, or incidents.  
- You want **agentic AI** that reasons over relationships, not only document snippets.  
- You need a **controlled self-host** environment for a pilot (team or LOB).  
- You want proof before committing to Enterprise-scale governance.

---

## How to get started

### What your team needs

| Role | Involvement |
|------|-------------|
| **Sponsor** | Names the pilot outcome (“reduce ticket handle time”, “account risk view”) |
| **Domain expert** | Confirms smart-review plan (“yes, these are customers vs tickets”) |
| **Technical owner** | Runs Docker Compose, Settings, security |
| **End users** | Ask questions; flag wrong links via Correct data |

### Install (technical owner — 15–30 minutes)

```bash
git clone https://github.com/giggsoinc/aryx.git
cd aryx
cp .env.example .env
docker compose pull
docker compose up -d
```

Open **http://localhost:3000**.

Full install: [INSTALL.md](../INSTALL.md).

### First business success path (guided)

1. **Pick one pilot** — e.g. support: customers + tickets (sample files included).  
2. **Create a workspace** named after the pilot (e.g. “Support Context”).  
3. **Load data first** — upload CSVs or connect a read-only database.  
4. **Smart review** — Aryx proposes what the data is and a graph plan; your domain expert light-edits.  
5. **Build** — Aryx resolves duplicates and builds the context graph.  
6. **Ask** — “Which customers have the most open tickets?” with sources you can open.  
7. **Share** — decide whether agents (Claude / internal bots) may use this workspace via IT.

Sample data: [`examples/quickstart/`](../../examples/quickstart/).

---

## Using Aryx with Claude, Gemini, or Copilot

Business outcome is the same no matter which chat brand you prefer:

> **Load data into Aryx once → agents answer from connected context with sources — not from guessing across five systems.**

Two different roles get confused. Keep them separate:

| Role | What it does | Who configures it |
|------|----------------|-------------------|
| **A. Brain inside Aryx** | The model Aryx uses for smart review, extraction, and **Ask** (Settings) | IT / technical owner |
| **B. Chat app you work in** | Claude, Gemini app, Microsoft Copilot, Cursor — where *you* type questions | You + IT |

You can use **Gemini as Aryx’s brain** and still ask questions in the **Aryx web UI**.  
You can use **Claude Desktop** as the chat app that *calls* Aryx via MCP.  
You can use **Copilot** as the chat app that works best through **your company’s app** that calls Aryx’s API (or the Aryx UI).

### The outcome path (all brands)

```text
1. Build context in Aryx (data first → smart review → build)
2. Pick how people ask:
      • Aryx Ask (web)     — works with any Settings model
      • Claude + MCP       — Claude tools talk to Aryx
      • Gemini / Copilot   — use Aryx Ask, or a company app/API bridge
3. Ask business questions; open cited sources when you need proof
4. Fix wrong links with Correct data so the next answer improves
```

### Option 1 — Stay in the Aryx app (simplest for business)

**Best for:** pilots, domain experts, no desktop agent setup.

1. IT runs Aryx (Docker) and sets **Settings → provider** (Ollama, Gemini, Claude/Anthropic, OpenAI, Grok, etc.).  
2. Your team loads the pilot data and builds the graph.  
3. Everyone uses **Ask** at http://localhost:3000 (or your company URL).  
4. Answers come with **citations** to entities / source records.

You do **not** need Claude Desktop or Copilot for this path. Gemini (or any model) is only the engine under Settings.

### Option 2 — Claude (Desktop / Code) with Aryx as tools

**Best for:** “Talk in Claude, but answers grounded in company context.”

| Step | Business | IT |
|------|----------|-----|
| 1 | Define pilot questions (“Which accounts have open escalations and expired contracts?”) | Run Aryx; open MCP on port **8765** (see [mcp-guide.html](../mcp-guide.html)) |
| 2 | Approve the smart-review plan so the graph is trustworthy | Connect Claude Desktop (or Claude Code) as an **MCP host** to Aryx — in-app **MCP** menu shows the URL + config |
| 3 | In Claude, ask in plain English | Claude calls Aryx tools (workspace, status, ask-style flows) |
| 4 | Demand sources if Claude cannot show them | Confirm network: Claude machine can reach Aryx MCP URL |

**What you should expect from Claude + Aryx**

- Claude is the **conversation UI**.  
- Aryx is the **context and identity layer**.  
- Good outcome: Claude uses Aryx instead of inventing which “Acme” is which.  
- Weak outcome: Claude answers from general knowledge — IT should fix MCP connection or you should fall back to Aryx **Ask**.

**Plain-language ask examples (after context is built)**

- “Summarize open tickets for customer Acme and list source records.”  
- “Which products appear most often with high-priority incidents?”  
- “What did we already load into the Support workspace?”

### Option 3 — Gemini (Google)

Two legitimate patterns:

| Pattern | What the business user does | What IT does |
|---------|----------------------------|--------------|
| **Gemini powers Aryx** | Use Aryx **Ask** / setup as usual | Settings → provider **Gemini** + API key; models chosen |
| **Gemini chat as the front door** | Use Gemini app/workspace only if IT built a bridge (custom Gemini agent that calls Aryx HTTP) | Wire Gemini tools/extensions to Aryx REST; or tell users to use Aryx Ask |

**Honest Lite reality:** Aryx does **not** ship a one-click “Google Gemini app marketplace plugin.”  
Fastest Gemini-backed outcome today = **Gemini in Settings + humans/agents use Aryx UI Ask (or your internal bot that calls Aryx API).**

### Option 4 — Microsoft Copilot

| Pattern | Business user | IT |
|---------|---------------|-----|
| **Copilot as chat only** | Prefer Aryx **Ask** for grounded company context | Ensure Aryx is available on the corp network |
| **Copilot Studio / custom agent** | Use the company Copilot agent your team published | Plugin/action that calls Aryx **REST Ask** (or entity APIs) with workspace id |
| **GitHub Copilot (coding)** | Devs use it while building apps *on top of* Aryx | Not the primary business Q&A path |

**Honest Lite reality:** Copilot does not automatically see your Aryx graph. Someone must **connect** it (custom agent + API), or people use the **Aryx web Ask** path.

### Choosing a path (decision table)

| If your company… | Start with |
|------------------|------------|
| Wants fastest pilot, mixed non-technical users | **Aryx Ask** (+ any Settings model including Gemini) |
| Already lives in Claude Desktop / Claude Code | **Claude + MCP → Aryx** |
| Standardizes on Google Gemini as the model vendor | **Gemini in Settings** + Aryx Ask (or Gemini custom agent later) |
| Standardizes on Microsoft 365 Copilot | **Aryx Ask** short-term; **Copilot Studio → Aryx API** for embedded experience |
| Needs “one agent many apps” | Build once on **Aryx API/MCP**; front-ends can be Claude, Copilot, or your portal |

### What “good outcome” looks like (checklist)

- [ ] Pilot data is in **one Aryx workspace**.  
- [ ] Smart review plan approved by a domain expert.  
- [ ] Ask (or Claude-via-MCP) returns an answer **plus** sources you can open in **Data**.  
- [ ] Wrong merges are fixed once in **Correct data**, not re-argued in every chat.  
- [ ] IT knows which path is supported: **UI only**, **Claude MCP**, or **API to Copilot/Gemini**.

### What you should not expect

| Expectation | Reality |
|-------------|---------|
| Install Claude and it “knows” ERP with no Aryx | Claude needs Aryx (or similar) + data loaded |
| Type into public Gemini with no setup | No company graph until Settings/API/UI path exists |
| Copilot Chat sees Aryx with zero IT work | Needs API/agent integration or use Aryx Ask |
| Any model alone replaces identity resolution | Models help; **Aryx keeps identity and links durable** |

---

## How to use (by business stakeholder)

### Product / LOB owner

| You care about | You do in Aryx |
|----------------|----------------|
| Pilot goal | Name workspace; write aim in smart review / brief |
| Time to demo | Data-first setup → Ask in same session when data is small |
| Scope control | One workspace per use case; don’t boil the ocean |
| Success metric | “Agent answered with correct account + ticket link + source” |

### Operations / support / sales ops

| You care about | You do in Aryx |
|----------------|----------------|
| Who is this customer? | Data explorer: entities, types, source records |
| Wrong merge or type | **Correct data** coach — propose, then Apply |
| Daily questions | **Ask** with citations — or Claude via MCP if IT enabled it |
| Preferred chat (Claude / Gemini / Copilot) | See [Using Aryx with Claude, Gemini, or Copilot](#using-aryx-with-claude-gemini-or-copilot) |
| Stuck jobs | Tell IT: Observe / Jobs; Resume if checkpoint exists |

### Data / analytics leadership

| You care about | You do in Aryx |
|----------------|----------------|
| Lineage | Provenance on entities |
| Model quality | Model canvas; Accuracy Lab |
| Sources | Prefer DB connect + files; document what was loaded |
| Scale limits | Lite is pilot/team scale; Enterprise for larger programs |

### Executive sponsor (CTO / CDO / CIO)

| You care about | You do |
|----------------|--------|
| Risk | Self-host; keys in Settings; BSL license for internal use |
| Path to scale | Lite proves value → Enterprise conversation for governance/scale |
| Integration with AI strategy | Aryx = context layer under Claude / Gemini / Copilot — not a replacement ERP/CRM |
| “Which chat brand do we standardize?” | UI Ask works with any Settings model; Claude MCP is strongest agent-native path; Copilot/Gemini fronts need API bridge or Ask |
| Commercial hosting of Aryx as SaaS | Requires commercial license ([LICENSING.md](../LICENSING.md)) |

---

## How Aryx fits the business architecture

```text
CRM · ERP · Tickets · Docs · Spreadsheets
              │
              ▼
     Aryx Lite (context layer)
     discover · resolve · graph · provenance
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
  People    Apps     AI Agents
  (UI Ask)  (API)    (MCP / tools)
```

- **Systems of record stay systems of record.**  
- Aryx **lands and links** copies/facts needed for resolution and audit—not “delete Salesforce.”  
- Agents consume **shared context** instead of reinventing it.

---

## Benefits summary

| Benefit | Business translation |
|---------|----------------------|
| Self-building context | Less manual model maintenance |
| Entity resolution | One customer, not five aliases |
| Provenance | Trust and audit |
| Agent-ready interfaces | Faster AI product delivery |
| Workspace isolation | Safe pilots per team |
| Data-first setup | Domain experts review a plan, not a blank form |

---

## Editions (keep short)

| | **Aryx Lite** (this repo) | **Aryx Enterprise** |
|--|---------------------------|---------------------|
| Fit | Team / pilot / self-host | Scale, governance, advanced agentic control |
| License | BSL 1.1 (internal use OK; competing SaaS needs commercial terms) | Commercial |
| Goal | Prove connected context for AI | Run it as enterprise platform |

See [EDITIONS.md](../EDITIONS.md).

---

## Further reading

| Doc | Audience |
|-----|----------|
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | Engineers & agent builders |
| [USER_GUIDE.md](../USER_GUIDE.md) | Day-to-day product UI |
| [UI_BUSINESS_FLOW.html](../UI_BUSINESS_FLOW.html) | Visual product path |
| HTML twin | [BUSINESS_GUIDE.html](BUSINESS_GUIDE.html) |

---

*Aryx Lite — connect your data, build business context, give AI agents something real to reason over.*
