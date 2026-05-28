# doc_delta — Documents into Aryx: the debate → decision filters

**Status:** proposal (HITL — review before any build)
**Mode:** Andie Drama (panel debate)  ·  **Date:** 2026-05-28
**Scope:** Extend Aryx from DB-row ingestion to **documents** (PDF, PPT, RTF, JSON)
with **Claude-via-MCP** as the query/output surface. Plan-first; no implementation.
**Companion:** full technical design in [doc_delta_tech.md](./doc_delta_tech.md).

> Note: a "scope doc" was referenced for the MCP-output decision but does not
> exist in-repo. MCP-as-output is captured here as a **stated requirement**, not
> a derived one. If a real scope doc exists, reconcile against it before build.

---

## Panel

- **Functional — Knowledge Analyst:** owns the question a user actually asks
  ("how is Acme in this contract related to our Acme customer record?").
- **Technical — Pipeline/Platform Eng:** owns connectors, the Broker, storage
  planes, the MCP server, failure modes.
- **Data — Ontology/ER Steward:** owns extraction quality, lineage/provenance,
  cross-source resolution, the HITL gate.
- **Boundary Pusher:** challenges the deterministic-first cost model.
- **Blocked Dev:** challenges anything that delays a runnable demo.

---

## The debates

Each debate states the question, the strongest opposing positions, the direct
disagreement, and the **decision filter** — the reusable criterion that settles
it (and will settle similar future calls).

### D1 — How does a document become graph data?

- **Position A (chunk-as-record):** split the doc into chunks; each chunk is a
  record. Great for embeddings/recall; chunks are *not* entities, so the graph
  stays empty of meaning.
- **Position B (entity-extraction-as-record):** an LLM reads the doc and emits
  structured entity *mentions* + stated relations; each mention is a record that
  flows the existing resolve→relate→project pipe. Rich graph; risks hallucinated
  entities; loses full-text recall.
- **Disagreement:** Analyst wants citations to exact passages (favors A);
  Steward wants clean entities in the graph (favors B).
- **Decision filter:** *Does the output need both a faithful citation and a graph
  node? If yes, you need both representations.*
- **DECISION → Hybrid B+C (GraphRAG).** Parse → **chunk + embed** (semantic layer
  for recall/citation) **and** run an **extraction agent** that emits entity
  mentions + relations (graph). The two are joined by shared provenance
  (`doc_id`, `chunk_id`, char span). This reuses the `Connector → RawRecord`
  seam: the doc connector yields mention-records; chunks land in the vector plane.

### D2 — Where do documents live? (user: "docs in RDB = V BAD IDEA")

- **Position A (RDB rows):** keep everything in Postgres like DB ingestion.
  Rejected — bloats the RDB, no semantic search, wrong tool.
- **Position B (pgvector + blob + RDB-for-metadata):** raw files in **S3**;
  parsed **chunks + embeddings + semantic tags in pgvector**; **metadata,
  entities, provenance, relations stay in Postgres** (as today); FalkorDB stays
  the projection.
- **Disagreement:** none material — the user's instinct and the Steward agree;
  the only question is whether pgvector is a new DB or an extension of the
  existing Postgres.
- **Decision filter:** *RDB stays the system-of-record for facts and lineage;
  unstructured semantics live in the vector plane; bytes live in blob storage.*
- **DECISION → Four planes.** S3 (bytes) · Postgres (facts + lineage) · **pgvector
  extension on the existing Postgres** (chunks/embeddings/tags) · FalkorDB
  (graph). One Postgres instance, `vector` extension added — not a second DB.

### D3 — Is the output REST, Streamlit-chat, or MCP? (user: firm on MCP)

- **Position A (REST/Streamlit chat):** ship a chat UI over the REST API.
  Rejected — rebuilds an LLM client Aryx shouldn't own; weak provenance UX.
- **Position B (Aryx MCP server):** expose graph + vector as **MCP tools**;
  Claude is the chat client. NL → Claude selects tools → answer with citations.
- **Decision filter:** *Aryx owns retrieval truth + tools; the LLM client is not
  Aryx's to build. Ship tools, not a chatbot.*
- **DECISION → MCP is the primary query surface.** The Increment-6 REST API is
  **retained** as internal/programmatic access and as what the MCP server calls;
  it is not wasted. GraphReader stays the read core under both.

### D4 — "Why deterministic-first? Even that can use an LLM router."

- **Boundary Pusher:** every stage could route to an LLM per item; deterministic
  fast-paths are a premature optimization.
- **Platform Eng:** at millions of rows/chunks, an LLM-per-item is unaffordable
  and non-reproducible; determinism is also a *correctness/audit* property.
- **Decision filter:** *Default to the cheapest path that is correct; let a router
  escalate per-item by measured difficulty under a budget — never escalate by
  default.*
- **DECISION → Deterministic-first WITH per-item router escalation.** The Broker
  already has tiers + a `TokenGovernor` that downgrades on budget. Generalize it:
  every stage computes a cheap **difficulty/ambiguity score**; only items over a
  threshold escalate up the tier ladder. The user is right that a router applies
  everywhere — it just decides *when to spend*, not *spend always*.

### D5 — JSON: structured or document?

- **Position A (treat as docs):** chunk + embed the JSON text. Loses its keys.
- **Position B (flatten to records):** JSONPath flattens objects to field→value
  records (like the DB path). Loses long free-text values.
- **Decision filter:** *Honor whatever structure exists; treat only free-text
  leaves as document content.*
- **DECISION → Hybrid JSON connector.** Flatten keys → records (DB path); route
  long free-text string leaves through the chunk+embed path (doc path). JSON is
  the bridge case that exercises both pipes.

### D6 — Onboarding & the `.model.env`: Streamlit or Claude?

- **Position A (Streamlit wizard):** visual roll-call of discoverable models
  (`Broker.models()`), pick tier→model, enter keys, write `.model.env`.
- **Position B (Claude-guided via MCP):** Claude walks the user through, validates
  keys live, writes `.model.env`. Keeps the user in one tool (the output tool).
- **Decision filter:** *Meet the user in the tool they already opened; the
  artifact (`.model.env`) must be identical regardless of path.*
- **DECISION → Claude-guided onboarding first** (output is Claude/MCP anyway),
  with a **minimal Streamlit fallback** for non-Claude/visual setup later. Both
  emit the same `.model.env`. Secrets never committed; Raven secret-guard applies.

### D7 — HITL experience (new types, low-confidence merges)

- **Functional + Steward:** approvals must be fast and in-context, with the
  evidence (source passages) attached.
- **Decision filter:** *Every HITL decision shows its evidence and is recorded as
  a reusable label.*
- **DECISION → HITL via Claude/MCP elicitation.** A `pending_decisions` MCP tool
  surfaces proposed types and ambiguous merges with their source chunks/rows;
  the human approves/renames/rejects/merges in chat. Decisions persist as labels
  (the V2 ER-classifier training set). A Streamlit queue is a later alternative,
  not the first cut.

### D8 — PII detection: LLM flag or a dedicated local library?

- **Position A (LLM `is_pii` flag):** the tagger already flags PII. Simple — but
  non-deterministic, costs tokens, and *sends candidate PII to a model to ask if
  it's PII* — i.e. egress **before** the gate.
- **Position B (Presidio, local):** Microsoft Presidio (MIT) detects + anonymizes
  PII on-box (recognizers + local NER + context). Deterministic, free, no egress.
- **Disagreement:** none strong — A loses on egress alone; you cannot ask a remote
  model "is this PII?" without first sending it the PII.
- **Decision filter:** *Detect PII with a local, deterministic tool before any
  egress; never send candidate PII to a remote model to classify it.*
- **DECISION → Presidio first, LLM escalation only on ambiguity**, plus a per-type
  **policy table** (keep-hashed match key / mask / hash / drop). High-value keys
  (email, phone) stay usable for resolution as hashes while never egressing clear.
  *Accepted 2026-05-28 — policy table fixed; see doc_delta_tech.md §2.5.*

---

## Decision filters (reusable, lift these into future calls)

1. Need both a citation and a graph node → keep **both** chunk and entity reps.
2. RDB = facts + lineage; vector plane = semantics; blob = bytes.
3. Ship **tools, not a chatbot** — the LLM client isn't Aryx's to own.
4. Cheapest-correct by default; **router escalates per-item under budget**.
5. Honor existing structure; only free-text leaves become document content.
6. Meet the user in the tool already open; artifacts identical across paths.
7. Every HITL decision carries its evidence and becomes a label.
8. Detect PII with a **local deterministic tool before any egress**; never send
   candidate PII to a remote model to classify it.

---

## Cross-source magic (why this is worth it)

The payoff is **one canonical "Acme"** resolved across a contract PDF, a Salesforce
record, and a `customers` row — with provenance edges back to the exact passage
and the exact row. Documents and databases resolve into the *same* entities; the
graph is the join. That is the thing REST-only or chat-only cannot deliver.

---

## Open questions (need a human answer before build)

- **Extraction model floor:** which tier is the minimum trustworthy extractor?
  Affects cost and the `.model.env` defaults. (Pre-mortem: bad extraction poisons
  the graph silently.)
- **Re-resolution on new docs:** full rebuild (current `project_graph` model) vs
  incremental — defer to batch rebuild for v1, same as the DB path.
- **MCP transport/auth:** local stdio (Claude Desktop/Code) vs remote HTTP MCP
  with auth — start local.

---

## OODA (convergence)

- **Observe:** all required seams exist (Connector, Broker+router, proposed-type
  gate, project_graph, GraphReader). No doc connector, no vector plane, no MCP.
- **Orient:** this is an *additive* extension along known seams, not a rewrite —
  plus two genuinely new pieces (extraction agent, MCP server).
- **Decide:** adopt D1–D7 as proposals; sequence docs-first per the user.
- **Act:** technical scope + increment plan in
  [doc_delta_tech.md](./doc_delta_tech.md); await GO before building Increment 7.

---

## Handoff

- **Target:** `raven-plan` / `fastapi-specialist` (MCP server) + `db-specialist`
  (pgvector) + `dataeng-specialist` (extraction/ER) when build is approved.
- **Decisions accepted:** D1–D7 as proposals pending user review.
- **Risks:** extraction quality (poisons graph), PII egress, MCP auth, cost of
  per-item escalation if thresholds are wrong.
- **Next step:** user reviews this + the tech scope, then approve Increment 7
  (doc connector + extraction + vector plane) as the first slice.
