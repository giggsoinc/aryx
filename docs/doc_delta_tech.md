# doc_delta_tech — Technical scope: documents + MCP output

**Status:** proposal (HITL — review before build)  ·  **Date:** 2026-05-28
**Decisions sourced from:** [doc_delta.md](./doc_delta.md) (D1–D7).
**Goal:** ingest PDF/PPT/RTF/JSON, resolve their entities into the *same* graph as
DB sources, and query everything from **Claude via an MCP server**.
**Non-negotiables carried from the codebase:** RDB stays system-of-record;
FalkorDB stays a rebuildable projection; provider-agnostic Broker; HITL gate on
new ontology types; provenance on every node/edge; no secrets in git.

---

## 1. Target architecture — four storage planes

```
                         ┌──────────────────────────────────────────────┐
  raw files ─► S3/blob   │ bytes (PDF/PPT/RTF/JSON), immutable, by hash  │
                         └──────────────────────────────────────────────┘
  facts/lineage ─► Postgres   (existing: runs, landed_records, entities,
                               members, relationships, ontology, mappings)
  semantics ─► Postgres+pgvector   (NEW: chunks, embeddings, chunk tags)
  graph ─► FalkorDB   (projection: entities, [:REL], [:FROM] provenance)
```

One Postgres instance; add the `vector` extension (no second DB — D2). S3 holds
the original bytes so the RDB never stores blobs; everything is rebuildable from
S3 + Postgres.

---

## 2. The document pipe (stage-by-stage, vs the existing DB pipe)

The existing pipe is `EXTRACT→CLEAN→PROFILE→LAND→TAG→MAP→RESOLVE→RELATE→PROJECT→QUERY`.
Documents reuse every seam; the deltas:

### 2.1 Extract — `connectors/document.py` (new), `connectors/json_source.py` (new)
- Conforms to the existing `Connector` ABC (`extract() -> Iterator[RawRecord]`).
- **Parse** by type: PDF (`pymupdf`), PPTX (`python-pptx`), RTF (`striprtf`),
  JSON (native). One parser registry keyed by extension/MIME.
- **Two emissions per doc:**
  1. **Chunks** → land in the vector plane (text + offsets + page/slide).
  2. **Entity-mention records** → `RawRecord{ source:{system,dataset=doc_id,
     record_id=mention_id}, payload:{type, name, attrs..., chunk_id, span} }`
     produced by the extraction agent (2.3). These flow the normal pipe.
- **JSON connector (D5):** JSONPath-flatten objects → field→value records (DB
  path); long free-text leaves → chunk+embed (doc path).

### 2.2 Clean — `pipeline/clean_text.py` (new)
- Text normalization distinct from row-clean: unicode NFC, de-hyphenation across
  line breaks, header/footer/boilerplate stripping, whitespace collapse.
- Chunking: structure-aware (page/slide/section) with overlap; deterministic, no
  LLM.

### 2.3 Profile — **new Document Profiling/Extraction Agent** (user: "another agent?")
- Yes — doc profiling ≠ field stats. New agent `ontology/extract.py`:
  - doc-type classification, language, section segmentation;
  - **entity-mention + relation extraction** (typed mentions, attributes, and
    explicit stated relations) returned as structured JSON via the existing
    `complete_json(broker, tier, system, user, schema)` path.
- Tiered + **router-escalated** (D4): cheap/local first; escalate a chunk to a
  higher tier only when an ambiguity score crosses threshold.
- **Verbatim-span gate (correctness, deterministic, free):** every emitted mention
  must cite a source span that *literally contains* the name; reject otherwise.
  Kills most hallucinations before any downstream cost — a control, not just a
  mitigation (see §9).

### 2.4 Land
- Chunks + embeddings + chunk tags → **pgvector tables** (§4).
- Mention metadata + provenance → **Postgres** (existing `landed_record` model,
  extended with `chunk_id`/`span`).
- Raw file → **S3**, addressed by content hash; `doc` row references the key.

### 2.5 Tag + PII gate — `pipeline/tag.py` (cheap tier) + `pipeline/pii.py` (new)
- Semantic tagging: classify chunk/section type (`clause`, `intro`, `table`),
  topic — reuse the cheap-tier tagger.
- **PII detection = Microsoft Presidio (local, deterministic, MIT)** — not the LLM
  flag. Presidio Analyzer (regex recognizers + local spaCy NER + context) finds
  PII spans on-box; Presidio Anonymizer applies the action. This *is* the
  no-egress mitigation: PII is found and masked **before any text or embedding
  leaves the machine**. Deterministic-first (D4); the LLM `is_pii` flag is demoted
  to escalation only for chunks Presidio scores as ambiguous. Custom recognizers
  cover domain PII (internal account ids) via the DD/ontology seam.
- **Per-type PII policy (ACCEPTED 2026-05-28):** each PII type maps to an action.
  High-value identifiers are kept as a **hashed** match key (SHA-256 of the
  normalized value) — usable for cross-source resolution but never sent to a
  frontier model in clear:

  | PII type | Action | Rationale |
  |---|---|---|
  | email, phone | **keep (hashed)** | strongest cross-source match key; hash collides across PDF↔DB; never clear to a model |
  | person / org name | **keep** | the entity label itself — can't redact the node; auditable via provenance |
  | address | **hash** | weak/partial match key, kept as hash |
  | SSN, national id, credit card, medical, financial account | **mask / drop** | sensitive; clear value lives only in access-controlled S3 original |
  | any other detected PII | **mask (default)** | fail-safe default |
- **Span provenance:** PII spans stored per chunk (`aryx_pii_span`) so redaction
  is auditable and reversible by authorized users; original bytes stay only in
  access-controlled S3.
- **Egress boundary is fail-closed:** any chunk with un-actioned PII spans is
  blocked from leaving the box.

### 2.6 Map to ontology — reuse `ontology/mapping.py` `categorize()`
- **Postgres path (unchanged):** table→type, field→attribute, new types land
  `proposed`.
- **Doc path:** the extraction agent proposes a *type per mention class*; these
  reconcile against the live ontology via the same `categorize()` grounding and
  the **same `proposed` HITL gate**. `SchemaMapping` generalizes from
  field→attribute to mention-attribute→ontology-attribute.

### 2.7 Resolve — reuse `resolution/` funnel, new blocking key
- Resolve **mentions across docs and across docs↔DB** into canonical entities.
- Blocking adds **entity-name embeddings from pgvector** as a candidate key
  (alongside exact/fuzzy). This is what makes "Acme" in `contract.pdf` collide
  with "Acme Corp" in `customers`.
- Adjudication: frontier tier on the ambiguous middle only (unchanged economics).

### 2.8 Relate — extend `relationships.py`
- DB: foreign keys + co-occurrence (deterministic) — unchanged.
- Docs: (a) **co-occurrence** within a chunk/section (deterministic), (b)
  **LLM-extracted explicit relations** from text (`Acme —acquired→ Beta`),
  router-escalated. Higher LLM share than the DB path, by nature.

### 2.9 Project — reuse `project.py` `project_graph()`
- One **unified** FalkorDB graph from the RDB. `[:FROM]` provenance now points at
  **rows AND chunks**; add a `:Chunk`/`:Document` source node variant so a node
  can cite an exact passage. Still wipe-and-rebuild.

### 2.10 Query — **new Aryx MCP server** (D3) + retained REST (Inc 6)
- See §3. GraphReader + a new `VectorReader` are the read core under both.

---

## 3. MCP query layer (the output)

- **`mcp/server.py` (new)** — FastMCP server exposing Aryx as Claude-native tools.
  Calls `GraphReader` (graph) and a new `VectorReader` (pgvector) directly, or via
  the Increment-6 REST API as transport.
- **Tool surface (read):**
  - `search_entities(type?, name?, limit)` → entity list (wraps GraphReader)
  - `get_entity(id)` / `neighbors(id)` / `provenance(id)` → graph reads
  - `semantic_search(query, k)` → top-k chunks from pgvector, with doc citations
  - `graph_rag(question)` → hybrid: vector recall → entity expansion → subgraph +
    passages returned for Claude to synthesize **with citations**
- **Tool surface (HITL, D7):**
  - `pending_decisions()` → proposed types + ambiguous merges with evidence
  - `decide(decision_id, action, value?)` → approve/rename/reject/merge; persists
    a label
- **Tool surface (onboarding, D6):**
  - `list_models()` → `Broker.models()` roll-call
  - `write_model_env(config)` → validates + writes `.model.env` (never to git)
- **Transport:** local stdio for Claude Desktop/Code first; remote HTTP MCP with
  auth later. Governed by Raven `mcp-guard`.

---

## 4. Data model / migrations (new)

New numbered SQL migrations (kept in `.sql` files per DB-Guard); pgvector via the
`vector` extension:

- `0006_vector.sql` — `CREATE EXTENSION vector;`
- `aryx_document` — `doc_id, system, dataset, s3_key, sha256, mime, pages, run_id`
- `aryx_chunk` — `chunk_id, doc_id, ordinal, text, page, char_start, char_end`
- `aryx_chunk_embedding` — `chunk_id, embedding vector(N)` + IVFFlat/HNSW index
- `aryx_chunk_tag` — `chunk_id, semantic_type, is_pii`
- `aryx_entity_name_embedding` — `entity_id, embedding vector(N)` (resolution
  blocking)
- extend `aryx_landed_record` (or a sibling) with `chunk_id`, `char_start/end`
  so a mention threads to its exact passage.

Embedding dimension `N` is fixed by the chosen local embed model (Broker
`embed()` → Ollama `nomic-embed-text`/`mxbai-embed-large`).

---

## 5. Onboarding & `.model.env` (D6)

- **`.model.env`** holds: provider list, per-tier model mapping, endpoints, API
  key *references* (not raw keys where avoidable), token budgets, embed model.
  Read by `broker.default_broker()` (today reads `catalog.json` + env) — extend
  to merge `.model.env`. Git-ignored; secret-guard enforces.
- **Claude-guided (first):** MCP `list_models()` → user picks tiers → Claude
  validates a live call → `write_model_env()`.
- **Streamlit fallback (later):** `ui/setup_app.py` roll-call wizard, same output.
- **Failure UX:** if no model serves a needed tier, the deterministic-only demo
  path runs (pin ontology type, skip mapping agent) so the user still sees a graph.

---

## 6. LLM routing (D4) — per-item escalation

- Extend `broker/governor.py`: alongside budget downgrade, add a
  `route(tier_hint, difficulty) -> Tier` that **escalates** an item up
  `TIER_LADDER` only when `difficulty >= threshold`.
- Each stage emits a cheap difficulty signal (e.g. resolution pair score band,
  extraction self-reported confidence, chunk ambiguity). Deterministic stays the
  default; the LLM is bought per-item, under the existing budget guardrails.

---

## 7. New dependencies (ALL via Raven CVE gate before commit)

- Parsing: `pymupdf`, `python-pptx`, `striprtf` (RTF), maybe `unstructured`
  (heavier — evaluate vs the lean set).
- Vector: `pgvector` (server extension) + `psycopg`-side helpers (already have
  `psycopg`).
- PII: `presidio-analyzer`, `presidio-anonymizer`, `spacy` (+ a language model,
  e.g. `en_core_web_lg`). Local, MIT; adds image size — acceptable for no-egress.
- MCP: `mcp` / `fastmcp`.
- Onboarding (later): `streamlit`.
- Each must be added to `requirements.txt` + manifest and pass the three-tier CVE
  check. Prefer the lean parser set over `unstructured` unless quality demands it.

---

## 8. Phasing (docs-first, per the user)

- **Increment 7 — E2E orchestrator (prereq, small):** chain the *existing* DB
  stages `discover → resolve_run → relationships → project_graph` into one CLI so
  *anything* can reach the graph. Needed before docs are worth running.
- **Increment 8 — Vector plane:** `0006_vector.sql` + chunk tables + `VectorReader`
  + Broker embed wired to a real local model.
- **Increment 9 — Document connector + extraction agent:** `connectors/document.py`,
  `pipeline/clean_text.py`, `ontology/extract.py`; land chunks + mentions.
- **Increment 10 — Cross-source resolution + relate for docs:** name-embedding
  blocking; doc relation extraction; unified `project_graph`.
- **Increment 11 — MCP server:** read tools + `graph_rag` + HITL + onboarding
  tools; local stdio.
- **Increment 12 — Onboarding polish:** Claude-guided `.model.env`, Streamlit
  fallback, PII redaction gate.

JSON connector slots into Inc 9 (it is the hybrid bridge case).

---

## 9. Risks & mitigations

- **Extraction poisons the graph (highest):**
  - *Failure modes:* the model invents entities absent from the text; one real
    thing typed many ways (type drift); an attribute lifted from the wrong span;
    resolution over-merges and amplifies one bad mention; all **silent**.
  - *Detection signals:* % mentions below the confidence floor; new-type proposals
    per run (spike = drift); mentions whose name is **not present** in their cited
    span; HITL reject rate; name-embedding cluster purity.
  - *Controls:* **verbatim-span gate** (deterministic, free — reject any mention
    whose name is absent from its cited span; §2.3); confidence floor →
    low-confidence lands `proposed`, never auto-merge; new types always HITL;
    per-attribute provenance for trace + reversal; **canary doc set** as a
    regression gate before each scale-up.
  - *Owner:* Ontology/ER Steward. *Fail-safe:* graph is wipe-and-rebuild from the
    RDB, so a bad run is fully reversible.
- **PII egress (chunks carry more PII than columns):**
  - *Failure modes:* clear-text PII reaches a frontier model or the embedding
    store; over-redaction destroys a valuable match key (email); novel PII missed.
  - *Detection signals:* Presidio recall on a labelled PII canary set; count of
    un-redacted PII spans reaching the egress boundary (must be **zero**);
    match-key coverage after redaction.
  - *Controls:* **Presidio** local detect + anonymize gate before any egress;
    per-type policy (keep-hashed match keys vs mask/hash/drop); local embed model;
    OpenAI endpoints already blocked in manifest; HITL on the policy table.
  - *Owner:* Ontology/ER Steward + Security. *Fail-safe:* egress boundary is
    **fail-closed** — a chunk with un-actioned PII spans cannot leave the box.
- **Cost blow-up from mis-tuned routing:**
  - *Failure modes:* difficulty thresholds too low → everything escalates to
    frontier; the adjudication band too wide; extraction retries multiply tokens;
    a re-resolution rebuild re-LLMs everything already computed.
  - *Detection signals:* tokens-per-record by tier trending up; % items escalated
    above cheap; frontier spend as % of total; per-run burn vs run size.
  - *Controls:* **fail-closed budget ceilings** in `TokenGovernor` (on exhaustion,
    stop escalating — queue for HITL or land low-confidence, never silently
    overspend); per-run budget cap with abort; **conservative default thresholds**
    (escalate rarely, raise only with evidence); **content-hash LLM cache** so a
    chunk/pair is never re-LLM'd across reruns (decisive for rebuilds); spend
    alerts at 25/50/75/90% mirroring Raven's token thresholds.
  - *Owner:* Platform Eng. *Fail-safe:* budget exhaustion downgrades/queues;
    rebuilds hit the cache, not the model.
- **MCP exposure / auth:**
  - *Failure modes:* HTTP MCP exposed without auth; a write/delete tool reachable;
    tools return PII in clear; tool args string-built into Cypher/SQL (injection);
    prompt-injected document text steers Claude toward destructive tool calls.
  - *Detection signals:* unauthenticated calls; tool-call audit gaps; outputs with
    un-redacted PII; anomalous traversal depth/result size.
  - *Controls:* **local stdio only for v1** (no network); **read-only tool surface**
    (no write/delete via MCP); when remote — OAuth + per-client scopes behind Raven
    **mcp-guard** (hard mode); **parameterized queries only** (GraphReader already;
    VectorReader must); outputs honor the PII policy; **treat retrieved document
    text as untrusted** — tools return data, Claude decides; never derive tool args
    from unvalidated retrieved content.
  - *Owner:* Platform Eng + Security. *Fail-safe:* default-deny; remote stays
    disabled until auth + mcp-guard hard mode are in place.
- **Embedding model / dim lock-in:**
  - *Failure modes:* switching embed model changes dim or vector space → old
    vectors incomparable; mixed-model vectors in one index → garbage similarity;
    same dim but different model degrades **silently** (no error, worse results).
  - *Detection signals:* stored model id ≠ configured model at startup; index dim
    vs config mismatch; semantic_search relevance drop on a canary query set.
  - *Controls:* **store model id + dim with every vector**; startup **fail-closed**
    on mismatch until re-embed; **per-model index** (build the new one alongside,
    then cut over — never mix spaces); a **re-embed job** (vector plane rebuilds
    from chunks in Postgres/S3); canary relevance regression gate after any change.
  - *Owner:* Platform Eng. *Fail-safe:* vector plane fully rebuildable; spaces
    never mixed.

---

## 10. Out of scope (now)

- A bespoke chat UI (Claude is the client — D3).
- Incremental re-resolution (batch rebuild for v1).
- Salesforce/Odoo connectors (manifest lists them; separate increments).
- Training an ER classifier (V2; HITL labels are the seed).

---

## Definition of done (Increment 7 + 8 + 9 slice)

A PDF dropped into a watched source is parsed, chunked, embedded, its entities
extracted and resolved against existing DB entities, projected to FalkorDB, and a
user in Claude can ask "what do we know about Acme?" and get an answer that cites
both the contract passage and the customers row. Until the MCP server (Inc 11),
the same is verifiable via the REST API + `semantic_search`.
