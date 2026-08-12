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
| Daily questions | **Ask** with citations |
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
| Integration with AI strategy | Aryx = context layer; not a replacement ERP/CRM |
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
