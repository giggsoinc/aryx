# Aryx — Knowledge Graph Platform

**Aryx** ingest records from databases and documents, resolves duplicate records across sources into single entities, infers relationships, and builds a searchable knowledge graph. Use it to reason over messy, multi-source data—customers from Postgres and Salesforce, support tickets from email and Jira, products from inventory and e-commerce—all deduplicated and linked in one place.

## Features

- **Multi-source ingest** — Connect Postgres, MySQL, Oracle, or upload CSV/PDF/Word documents
- **Auto-discovery** — AI agent maps your schema to entities; no ontology upfront
- **Record resolution** — Deduplicates and merges records across sources via deterministic blocking + frontier LLM
- **Knowledge graph** — Interactive graph visualization; path queries between entities
- **Chat interface** — Ask natural-language questions about your data; LLM answers with source provenance
- **Workspace isolation** — Separate projects (Customer Support, Sales, BoM) with independent graphs
- **Local + cloud models** — Runs cheap Ollama models locally; optionally uses Claude/OpenAI for high-value decisions
- **Human-in-the-loop ER** — Ambiguous merges queue for steward review; every decision (human or LLM) persists as labeled training data
- **Survivorship policies** — Per-workspace JSON merge rules (source-trust, most-recent, most-complete, most-frequent) with a per-attribute conflict audit trail
- **Auditable confidence** — Every entity carries a confidence derived from its weakest merge decision (never claims 1.0)
- **Actions (kinetic layer)** — Declarative, human-approvable mutations with full before/after audit; external agents can request actions via MCP but never auto-apply
- **Scale + resume** — Chunked block-wise resolution (memory bound = largest block) and stage-level checkpoints; crashed pipelines resume instead of restarting
- **Measured quality** — `make er-bench` publishes precision/recall on labeled datasets (Febrl): P=1.00 / R=0.59 / F1=0.74 on Febrl1; the band design comes from the measured sweep, not opinion

## Quick Start

**Prerequisites:** Docker, Docker Compose, git

```bash
git clone https://github.com/giggsoinc/aryx.git
cd aryx
docker compose up -d
# UI: http://localhost:8501
# API: http://localhost:8088
```

First time? Go to **Ingest tab** → provide context (e.g., "Customer support data") → connect a Postgres database or upload CSVs.

**📊 Architecture Diagrams:**
- [Business View](docs/diagrams/business-view.html) — What users see and backend flow
- [Technical Flow](docs/diagrams/technical-flow.html) — 4-layer system architecture

## Documentation

- **[Install Guide](docs/INSTALL.md)** — Setup locally or on EC2
- **[User Guide](docs/USER_GUIDE.md)** — Walk through UI, ingest workflow, querying
- **[Ingestion Guide](docs/INGESTION_GUIDE.md)** — Step-by-step for database and document ingest
- **[Architecture](docs/ARCHITECTURE.md)** — System design, components, data flow
- **[Gap-Closure Program](docs/wiki/PROGRAM_CLOSE.md)** — Bench history, decisions index (DEC-001..006), v2 backlog
- **[Benchmarks](docs/wiki/BENCHMARKS.md)** — Append-only measured P/R/F1 rows
- **[RDF Export & Integration](docs/RDF_EXPORT_GUIDE.md)** — Export to semantic web tools, SPARQL, data lakes, LLM pipelines

## Stack

- **Backend:** FastAPI + Postgres + FalkorDB + Ollama
- **Frontend:** Streamlit (web UI)
- **Deployment:** Docker Compose (local), EC2 (production)
- **Models:** Ollama (local), Anthropic Claude (optional frontier tier)

## Contributing

See [CLAUDE.md](CLAUDE.md) for development practices (Raven discipline).

## License

MIT
