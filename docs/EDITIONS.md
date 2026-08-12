# Aryx — Editions

Aryx ships in three editions off one codebase. The split is deliberate: the
**Lite** edition proves the idea and seeds adoption; the **Enterprise**
edition is the product the CFO/CDO/skeptic buy; **Aryx-o** is the same
Enterprise engine running natively on a hyperscaler's stack (Oracle ADB
first) — made possible because the core is built behind swappable ports.

| | **Aryx Lite** | **Aryx Enterprise** | **Aryx-o** |
|---|---|---|---|
| **Tagline** | A lightweight ontology layer for quick outcome mapping | The discovery-driven knowledge-graph platform | Aryx Enterprise, native on the hyperscaler |
| **Version** | v1.x | v2.x | v2.1+ |
| **Audience** | Teams, analysts, OSS users | Enterprise data + AI orgs | Oracle / Azure / GCP shops |
| **Substrate** | Postgres · FalkorDB · Ollama (bundled) | Pluggable adapters; commodity defaults | Native: Oracle ADB · Oracle RDF/Property Graph · AI Vector Search · OCI GenAI · Oracle OWL reasoner |
| **Scope** | Brief → ingest → resolve → map → Ask, single workspace, modest scale | Everything in the v2 design set (below) | Same Enterprise engine; substrate swapped via adapters, not surgery |
| **Licensing** | **BSL 1.1** (→ GPL-3.0-or-later on 2029-07-15) | Commercial EULA | Commercial EULA |

## Aryx Lite (v1.7) — what it is today

The currently shipped app (**1.7.0**): Home workspaces, **data-first** guided
setup (`/start` — smart brief + graph plan), Brief edit page, Ask with
grounded answers + citations, Model canvas, Data explorer with **Correct data**
coach, Accuracy Lab, Observe, Settings, MCP, ingest from DB + files, dimension
materialization from plan, entity resolution, survivorship, RDF/OWL
import-export. It runs on the bundled Postgres + FalkorDB + Ollama stack (or
cloud LLMs via Settings). Fast front door for a single team — not a 200M-row
multi-tenant estate.

### Data-first smart setup (Lite product rule)

Setup is **data first**, then AI-assisted understanding:

1. Point Aryx at files or a database.  
2. The configured **answer model** (Gemini, Claude, OpenAI, Grok, Ollama — whatever is in Settings) reads samples and drafts the **brief + graph plan**.  
3. User lightly corrects, optionally adds more documents Aryx suggests.  
4. Confirm → brief saved → ingest builds the graph (types, dimensions, links).

Users must not invent six blank brief answers before Aryx has seen data.
Provider is swappable; the foundation is the same. See pack note
`Audit-Postmortem/packs/OSS_Lite_Polish_Pack/DATA_FIRST_SMART_SETUP.md`.

Lite gets **UI polish, data-first smart understand, and deterministic multi-type
hooks** for tabular columns. The full **agentic ontology control plane**
(EDA sizing, multi-agent Stage-2, pathway gates, full agent tracing) ships on
the **Enterprise fork**, not as default open-source scope.

> Lite is intentionally *not* the enterprise product. It's the wedge: a
> clueless user reaches a useful ontology in minutes. **BSL 1.1** keeps
> that front door wide open for self-host and internal use, while blocking
> unlicensed competing SaaS re-hosts. See [LICENSING.md](LICENSING.md).

## Aryx Enterprise (v2) — what we're building

Enterprise is developed on a **separate commercial fork** (not the default
Lite path in this repository). It includes the v2 design set in
`temp_design/ontology-v2/` (Accuracy Lab at scale, connectors, governance,
reasoner, LLM router, pipeline observability, ports & adapters) **and** the
**agentic ontology control plane**: EDA / size-shape, pathway gate
(ontology vs RAG vs hybrid), Stage-2 micro-agents (types, keys, relationships,
brief alignment, critic), plan accept, and full tracing (at rest / in flight /
on completion).

Enterprise **extends** Lite’s data-first smart setup (same UX metaphor: load →
understand → confirm). It does not reintroduce brief-before-data. Delta:
`Audit-Postmortem/packs/EE_Ontology_Agentic_Pack/DATA_FIRST_SMART_SETUP_EE.md`.

See **`temp_design/ontology-v2/08-v2-attack-plan.html`** for the earlier v2
build order; agentic architecture packs ship to the Enterprise team separately.

## Aryx-o (v2.1) — native on the hyperscaler

The same Enterprise engine, but the commodity substrate is **removed** and
replaced by the platform's native services. On Oracle: drop FalkorDB for
Oracle's RDF/Property Graph + native OWL inferencing, drop pgvector for AI
Vector Search, drop Ollama for OCI GenAI, drop Postgres for Oracle ADB.

**This is only cheap if v2 is built right.** Aryx-o must be an *adapter
swap*, not a rewrite — which is why **Phase 0 of the v2 plan is the
ports-&-adapters seam**: define the capability interfaces first, wrap the
current Postgres/FalkorDB/Ollama implementations as the *default* adapters,
and load the adapter set from config. Then Aryx-o = write the Oracle
adapters + flip a config. No deep spinal-cord neurosurgery later.

---

*The Engine — ontology inference, entity resolution + survivorship, axiom
proposal, confidence/provenance/verification, the domain funnel, the
deliberation adjudicator, the HITL learning loop — is identical across all
three editions and never lives inside an adapter. That's the IP. The
substrate is commodity and swappable; the engine is the company.*
