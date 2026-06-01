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
