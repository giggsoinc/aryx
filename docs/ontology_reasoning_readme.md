# Ontology Reasoning — The Main Muscle

How Aryx turns tagged, profiled, landed data from many sources into a
knowledge graph: ontology mapping, entity resolution, relationships, and
projection. This is the design reference for Increment 5.

## What we are doing

After the data plane (Increments 1–2) and tagging (Increment 4), every source
record is landed in the RDB with provenance and its fields are semantically
tagged. The reasoning layer answers three questions:

1. **Ontology** — what *kinds* of things exist, and how do the kinds relate?
   (e.g. there is a `Customer`, an `Order`, and Customers place Orders.)
2. **Entities** — what are the actual *instances*? (e.g. "Acme Corp" is a Customer.)
3. **Resolution** — which records across systems are the *same real thing*?
   (Acme-in-Redshift == ACME-in-Oracle == "Acme" in a Drive contract.)

The output is a knowledge graph (FalkorDB): types = ontology, nodes = resolved
entities, edges = relationships, every node/edge traceable to its source rows.

## Myth to kill: "ML agents"

There is almost no classic ML training here — no labeled dataset, no model we
train (yet). The muscle is three layers, and knowing which does what is the
whole game:

| Layer | What it is | Why it exists |
|---|---|---|
| LLM reasoning | Claude (frontier) making judgment calls | "Are these the same? What type is this?" — needs understanding, not string match |
| Classical ER | string similarity, fuzzy match, blocking | cheap, deterministic, runs on millions of rows |
| Embeddings (the only real "ML") | vector similarity to find candidates | so the LLM never compares every pair |

The art: use the cheap layers to shrink the problem so the expensive LLM only
touches the hard ~1%.

## Part 1 — Ontology Mapping Agent (schema-level, frontier tier)

- **Input:** field tags + profiles + sample values per source dataset, plus the
  existing ontology.
- **Job:** map each source *table -> canonical entity type* and each *field ->
  canonical attribute*; propose new types when nothing fits.
- **Why an agent, not one call:** it reconciles against types it already
  created, detects conflicts, pulls more samples when unsure, and routes new
  types to a human review gate before they become real.
- **Volume:** tiny — once per source schema. Frontier cost is acceptable here.
- **Output:** stored schema mapping + proposed ontology types.

## Ontology sources — the plug (DD / MDM / schema.org)

The mapping agent is *grounded* by pluggable seed sources, mirroring the
connector and secret seams. There is no universal DD/MDM standard to flip on;
the real interchange standard is W3C **RDF / OWL / SKOS**.

```
OntologySource (protocol) -> load() -> [canonical types + attributes]
  - SchemaOrgSource      (built-in schema.org-style vocabulary, general)
  - DataDictionarySource (your DD: CSV/table — type, attribute)
  - MdmSource            (MDM export/API — future)
  - RdfOntologySource    (OWL/RDF/SKOS via rdflib — future)
```

Seed priority when available: **your DD/MDM (authoritative) > domain ontology
(FIBO/FHIR) > schema.org (general) > pure induction (last resort)**. Seeds are
scaffolding; the agent extends them from your data; humans curate. The system
runs with zero seed — schema.org just keeps type naming consistent.

## Callable agent contract

The mapping agent is invokable ad-hoc, not only in batch:

- `categorize(dataset profiles + tags, ontology) -> {type, attributes, confidence}` — "what is this?"
- `check(proposed type) -> {matches_existing, conflicts}` — "does this fit?" (future)

So a new table can be classified against the live ontology any time.

## Embeddings choice (correcting a common assumption)

Claude has **no embeddings API** — embeddings are a different model class.
Cheapest path: a **local Ollama embedding model** (`nomic-embed-text`,
`mxbai-embed-large`) — free, on the box. Added to the Broker as `embed()` on
the local tier. Web search (Perplexity) does **not** help mapping/resolution
(that is your private data, not the web) and risks data egress; reserve it as
an optional public **entity-enrichment** plug for v1.1+, off the critical path.

## Part 2 — Entity Resolution Agent (instance-level — the hard one)

Comparing every row to every row is n² — impossible at millions of rows. So it
is a funnel, and the LLM sits only at the bottom:

```
ALL records (millions)
   |  1. Normalize         (deterministic: lowercase, trim, standardize)
   v
   |  2. Block / candidates (classical + embeddings: group rows that MIGHT match)
   v   -> reduces millions^2 to a few candidates per record
   |  3. Score pairs        (cheap: string + attribute similarity)
   v   -> high score auto-merge, low auto-reject
   |  4. LLM adjudicate     (FRONTIER: only the ambiguous middle ~1-5%)
   v   -> "Acme Corp == ACME CORPORATION == 'Acme' in contract?"
   |  5. Cluster / merge    (deterministic: transitive closure -> one entity)
   v
Canonical entities, each with provenance to every source row
```

- **Blocking is make-or-break:** too loose is expensive, too tight misses
  matches (low recall). Candidate keys: exact-key, fuzzy (trigram/Levenshtein),
  embedding similarity.
- **The LLM only sees uncertain pairs** — this is token rationing in action.
- **Golden record:** when a cluster merges, pick the best value per attribute
  (most complete / most recent source).

## Part 3 — Relationship Inference

From foreign keys (deterministic) + co-occurrence + LLM for implied links ->
edges between resolved entities (`Acme -places-> Order#5`). Mostly cheap; the
LLM is used only for fuzzy/implied relationships.

## Part 4 — Storage (RDB stays the source of truth; migration 0003)

- `aryx_ontology_type` — canonical types + attributes
- `aryx_schema_mapping` — source field/table -> ontology type/attribute
- `aryx_entity` — resolved entity, type, golden attributes, confidence
- `aryx_entity_member` — entity <-> landed_record (cluster membership + provenance)
- `aryx_relationship` — entity -> entity edges

## Part 5 — FalkorDB projection (rebuildable from the RDB)

Type labels = ontology; nodes = resolved entities; edges = relationships plus
provenance threads back to source rows. Wipe-and-rebuild from Postgres anytime.

## Tier / cost map (rationing made concrete)

| Step | Tier | Why |
|---|---|---|
| Normalize, block, score, cluster | cheap / local / free | high volume, deterministic |
| Embeddings for blocking | local (ollama) or cheap API | scalable |
| Ontology mapping | frontier | low volume, hard reasoning |
| Resolution adjudication | frontier | only the ambiguous ~1-5% |

## Human-in-the-loop and provenance (non-negotiable)

- New ontology types and low-confidence merges pause for human approval before
  landing.
- Every type and merge records which source rows, which run, and what
  confidence — nothing in the graph is untraceable.
- V2 hook: human decisions become labels, enabling a trained ER classifier
  later. That is where real ML earns its place.

## Build plan — split Increment 5 into four sub-builds

Too big and too important for one shot; each is independently testable:

- **5a** — Ontology mapping agent + storage + HITL gate
- **5b** — Entity resolution funnel (normalize -> block -> score -> adjudicate -> cluster)
- **5c** — Relationship inference
- **5d** — FalkorDB projection

5a is the right first bite: it is the smaller agent, and resolution (5b) needs
canonical types to resolve into.

## Hardest risks

1. **Blocking recall vs cost** — the single most important tuning knob; bad
   blocking either misses matches or bankrupts the token budget.
2. **LLM non-determinism in mapping** — same input, slightly different ontology;
   hence versioning + human review.
3. **Embeddings dependency** — local (ollama, free, slower) vs API (fast, costs).
   A real decision to make before 5b.
4. **Re-resolution** — when new data lands, re-resolve everything or
   incrementally? Start batch / full re-resolve; optimize later.
