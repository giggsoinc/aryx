Feynman Style Explanation:

  Right now we have piles of labeled index cards from different filing cabinets. Ontology mapping decides "these cards
  are all Customers, these are Orders." Entity resolution decides "this Acme card and that ACME card are the same 
  company." Then we pin them on a board with strings between them. That board is the knowledge graph.

  What this means: ontology = the kinds of things; entities = the actual things; resolution = merging duplicates across
  systems; relationships = the strings. This is where raw data becomes knowledge.

  THE MAIN MUSCLE — every part broken down
  
  First, a myth to kill: "ML agents"

  There's almost no classic ML training here (no labeled dataset, no model we train). The muscle is three things working together — and knowing which does what is the whole game:
  
  ┌─────────────┬──────────────────────────────────┬────────────────────────────────────────────────────────────────┐
  │    Layer    │            What it is            │                              Why                               │
  ├─────────────┼──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ LLM reasoning           │ Claude (frontier) making      │ "Are these the same? What type is this?" — needs       │
  │                         │ judgment calls                │ understanding, not string match                        │
  ├─────────────────────────┼───────────────────────────────┼────────────────────────────────────────────────────────┤
  │ Classical ER            │ string similarity, fuzzy      │ Cheap, deterministic, runs on millions of rows         │
  │                         │ match, blocking               │                                                        │
  ├─────────────────────────┼───────────────────────────────┼────────────────────────────────────────────────────────┤
  │ Embeddings (the only    │ vector similarity to find     │ So we never ask the LLM to compare every pair          │
  │ real "ML")              │ candidates                    │                                                        │
  └─────────────────────────┴───────────────────────────────┴────────────────────────────────────────────────────────┘

  The art is using the cheap layers to shrink the problem so the expensive LLM only touches the hard 1%.

  ---
  Part 1 — Ontology Mapping Agent (schema-level, frontier tier)

  Input: the field tags + profiles + samples we already produce, per source dataset, plus the existing ontology.
  Job: map each source table → canonical entity type and each field → canonical attribute, and propose new types when
  nothing fits.
  - Redshift customers(email, name) + Oracle HZ_PARTIES(party_name…) → both map to one canonical type Organization;
  party_name→name, email→email.
  Why an agent (not one call): it must reconcile against types it already created, detect conflicts, pull more samples
  when unsure, and hand new types to a human review gate before they're real.
  Volume: tiny — once per source schema. So frontier dollars are fine here.
  Output: a stored mapping + proposed ontology types.

  Part 2 — Entity Resolution Agent (instance-level — the hard one)
  
  The scale trap: comparing every row to every row is n² — millions² is impossible and unaffordable. So it's a funnel,
  and the LLM is only at the bottom:
  
  ALL records (millions)
     │  1. Normalize        (deterministic: lowercase, trim, standardize)
     ▼
     │  2. Block / candidates (classical + embeddings: group rows that MIGHT match)
     ▼   → reduces millions² to a few candidates per record
     │  3. Score pairs       (cheap: string + attribute similarity)
     ▼   → high score = auto-merge, low = auto-reject
     │  4. LLM adjudicate    (FRONTIER: only the ambiguous middle ~1-5%)
     ▼   → "Acme Corp == ACME CORPORATION == 'Acme' in contract?"
     │  5. Cluster / merge   (deterministic: transitive closure → one entity)
     ▼
  Canonical entities, each with provenance to every source row

  - Blocking is the make-or-break step: too loose → expensive; too tight → misses matches (recall). Embeddings +
  exact-key + fuzzy keys generate candidates.
  - The LLM only sees the uncertain pairs — that's the rationing in action.
  - Golden record: when a cluster merges, pick the best value per attribute (most complete/recent source).
  
  ---
  Part 3 — Relationship Inference

  From foreign keys (deterministic) + co-occurrence + LLM for implied links → edges between resolved entities (Acme 
  —places→ Order#5). Mostly cheap; LLM only for fuzzy/implied relationships.

  ---
  Part 4 — Storage (RDB stays the truth; migration 0003)
  
  - aryx_ontology_type — canonical types + attributes
  - aryx_schema_mapping — source field/table → ontology type/attribute
  - aryx_entity — resolved entity, type, golden attributes, confidence
  - aryx_entity_member — entity ↔ landed_record (the cluster + provenance)
  - aryx_relationship — entity → entity edges
  
  Part 5 — FalkorDB projection (rebuildable from the above)

  Type labels = ontology; nodes = resolved entities; edges = relationships + provenance threads back to source rows.
  Wipe-and-rebuild from Postgres anytime.

  ---
  Tier / cost map (the rationing made concrete)
  
  ┌──────────────────────────────────┬────────────────────────────────────────┬────────────────────────────┐
  │               Step               │                  Tier                  │            Why             │
  ├──────────────────────────────────┼────────────────────────────────────────┼────────────────────────────┤
  │ Normalize, block, score, cluster │ cheap / local / free                   │ high volume, deterministic │
  ├──────────────────────────────────┼────────────────────────────────────────┼────────────────────────────┤
  │ Embeddings for blocking          │ local (ollama embeddings) or cheap API │ scalable                   │
  ├──────────────────────────────────┼────────────────────────────────────────┼────────────────────────────┤
  │ Ontology mapping                 │ frontier                               │ low volume, hard reasoning │
  ├──────────────────────────────────┼────────────────────────────────────────┼────────────────────────────┤
  │ Resolution adjudication          │ frontier                               │ only the ambiguous ~1-5%   │
  └──────────────────────────────────┴────────────────────────────────────────┴────────────────────────────┘
  
  
  Human-in-the-loop & provenance (non-negotiable)
  
  - New ontology types and low-confidence merges pause for human approval before landing.
  - Every type and merge records which source rows, which run, what confidence — so nothing in the graph is untraceable.
  - (V2 hook: human decisions become labels → then you could train a real ER classifier. That's where actual ML earns its
   place later.)
  