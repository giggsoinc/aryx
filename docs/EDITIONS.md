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
| **Licensing** | Candidate for **GPL** (open core) | Commercial | Commercial |

## Aryx Lite (v1) — what it is today

The currently shipped app: guided onboarding (`/start`), Ask with grounded
answers + citations, the Model canvas, MCP tooling, ingest from DB + files,
entity resolution, survivorship, RDF/OWL import-export. It runs on the
bundled Postgres + FalkorDB + Ollama stack. It is the **fast, approachable
front door** — quick outcome mapping for a single team, not a 200M-row,
multi-source, governed estate.

> Lite is intentionally *not* the enterprise product. It's the wedge: a
> clueless user reaches a useful ontology in minutes. GPL keeps that
> front door wide open.

## Aryx Enterprise (v2) — what we're building

Everything in `temp_design/ontology-v2/`: the Accuracy Lab, the scale
architecture (schema-not-rows, query-don't-render), Connectors at scale
(Salesforce/ServiceNow/Drive/warehouse, incremental sync), Governance
(domain/owner/sensitivity/lineage), Axioms + reasoner enforcement, the
SKOS relation registry, the surgical Deliberation Adjudicator, the per-task
LLM Router with sovereignty, pipeline observability + cost Governor, and the
ports-&-adapters modularity that makes the substrate swappable. See
**`temp_design/ontology-v2/08-v2-attack-plan.html`** for the build order.

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
