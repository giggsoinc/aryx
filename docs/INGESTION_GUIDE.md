# Ingestion Guide

## Overview (Assume You're a Fresher)

**Ingestion = turning messy source data into a clean, deduplicated knowledge graph.**

Think of it as a 7-stage assembly line:
1. **Extract** — Read from database or files
2. **Land** — Store raw records in Postgres with provenance (where did this come from?)
3. **Tag** — Cheap AI labels fields (email, phone, date, etc.)
4. **Map** — Human + AI agree on entity types (Person, Company, Product)
5. **Resolve** — Find duplicates, merge them into single entities
6. **Relate** — Draw edges between entities (Person works at Company)
7. **Project** — Build interactive graph in FalkorDB

**You only interact with steps 1–4. Steps 5–7 happen automatically.**

## Two Paths: Database vs. Documents

### Path A: Database Ingest

**When to use:** You have existing data in Postgres, MySQL, Oracle, etc.

**What you need:**
- Database credentials (host, port, user, password)
- One sentence describing the data: *"Customer accounts from Q2: include names, company, industry, deal size"*

**Step-by-step:**

1. **Provide context** (Ingest tab → Database tab → Step 1)
   - Text: Type a sentence about what's in your database
   - File: Upload a TXT/PDF/DOCX with entity descriptions
   - **Why?** AI agent uses context to understand which tables map to which entities

2. **Connect** (Step 2)
   - Fill form: RDBMS type, host, port, database name, user, password
   - Click **"Connect & introspect"** → system reads all table names + columns
   - Shows: "Found 47 tables"

3. **Auto-discover** (Step 3)
   - Click **"🤖 Run discovery agent"** → AI maps tables to entity types
   - Takes 30–60 seconds (depends on Ollama speed)
   - Proposes: Table "customers" → Entity "Person", Table "companies" → Entity "Company"

4. **Review & confirm** (Step 4)
   - Edit any row (change "Person" to "Customer" if you prefer)
   - Untick rows you don't want
   - **Match keys:** comma-separated list of columns that uniquely identify a record (usually "id")
   - Click **"Ingest selected tables"** → job starts

**What happens next:**
- Records stream from database into Postgres with provenance (source_system="postgres", record_id=original table PK)
- Fields get tagged (email, phone, currency, etc.)
- Cheap AI assigns records to entity types
- Duplicate records get merged (e.g., two "John Smith" entries become one entity with two members)
- Graph builds in FalkorDB
- Watch progress in **Observability tab** → **Jobs & Runs**

**Example (Postgres customer table):**

```
customers
├─ id (PK) → match key
├─ name → tagged "person_name"
├─ email → tagged "email"
├─ company_id (FK) → relationship hint (customer → company)
└─ created_at → tagged "date"

→ Context: "Customer accounts: names, emails, companies"
→ Agent maps: "This is a Person entity"
→ Records land, get tagged, deduplicated
→ Person entities appear in graph
```

### Path B: Document Ingest

**When to use:** You have unstructured data (PDFs, Word docs, CSV files, emails).

**What you need:**
- Files (PDF, PPTX, DOCX, CSV, JSON, images ≤2 MB each, max 50 files)
- One sentence: *"Customer support tickets: include customer names, product names, issue description"*

**Step-by-step:**

1. **Provide context** (Ingest tab → Documents tab → Step 1)
   - **Required:** Text or file; without it, discovery fails
   - Examples:
     - Text: *"Support tickets linking customers to issues to products"*
     - File: Upload a memo describing what's in the documents

2. **Upload files** (Step 2)
   - Drag & drop or click upload
   - System accepts: JSON, CSV, PDF, PPTX, DOCX, RTF, images (jpg, png, tiff)
   - Max 50 files, 2 MB each, 50 MB total

3. **Read & discover** (Step 2 button)
   - Click **"Read & discover"** → system extracts text from all files
   - Takes 10–30 seconds (PDF text extraction can be slow)
   - AI agent finds entity types in the text

4. **Review & confirm** (Step 3)
   - Checkboxes show entity types found: "Person (152 examples)", "Company (47 examples)"
   - Untick any you don't want
   - Click **"Confirm & add to graph"** → job starts

**What happens next:**
- Text extracted from each file (PDF → text, DOCX → paragraphs, CSV → rows)
- All text lands in Postgres with provenance (source_system="documents", source_file="invoice_q2.pdf")
- Cheap AI reads paragraphs, finds and tags entities
- Relationships inferred (e.g., "Customer X contacted support on Y")
- Graph builds

**Example (Customer support PDF):**

```
PDF: "ticket_001.pdf"
Content:
  "John Smith from Acme Corp called about product X not working.
   Escalated to supervisor. Resolved in 2 hours."

→ Context: "Support tickets: customer names, company names, products, issues"
→ Agent extracts:
   - Person: John Smith
   - Company: Acme Corp
   - Product: X
   - Relationship: Person → called → Product
→ Records land, deduplicated
→ Graph updated
```

## The Resolution Funnel (What Happens Behind the Scenes)

After records land, **5 merge** into entities automatically:

### Stage 1: Blocking (Cheap, deterministic)
- Groups records by exact match (name + email, or id = id)
- "John Smith, john@acme.com" + "John Smith, john@acme.com" → same block

### Stage 2: Scoring (Cheap, local AI)
- Compares each pair in a block
- Returns score 0.0–1.0: "How likely is this a duplicate?"
- Uses Ollama (fast, local)
- Example: "john smith john@acme" vs "john smith, jr" → 0.75 (probably same person)

### Stage 3: Adjudication (Frontier LLM, humans only)
- Only ambiguous pairs (0.4–0.6 score) go here
- Expensive Claude or human review (HITL gate)
- Example: "Michael Johnson, Chicago" vs "Michael Johnson, Denver" → frontier model decides

### Stage 4: Clustering (Transitive closure)
- If A ≈ B and B ≈ C, then A ≈ B ≈ C
- UnionFind merges transitive groups into single entities
- Result: one Person entity with 3 merged members (original records)

**Why this design?**
- Blocks eliminate 99% of comparisons (n² → n log n)
- Cheap model scores 95% of remaining pairs
- Only 1–5% go to expensive frontier model
- Humans only review high-stakes merges

## Monitoring Ingest

Go to **Observability tab**:

- **Jobs & Runs** — shows each ingest job (status, progress, stage, timeline)
- **LLM Tokens** — cumulative tokens used (cost tracking)
- **Graph Stats** — entity count, relationship count, last rebuild

Example job:

```
Source: postgres.public_customers
Status: ⏳ Running
Stage: Resolve (stage 5b)
Progress: 87%
Elapsed: 3 min 24 sec
```

## Troubleshooting

### Document discovery finds nothing

**Error:** "I couldn't recognise anything. Try clearer files..."

**Causes:**
- Context too vague ("customer data" vs. "customer accounts Q2 with names, company, industry")
- Files mostly images/diagrams with no text (scanned PDFs need OCR)
- Files are encrypted or corrupted

**Fix:**
- Click 🔄 **Reset**
- Provide more specific context (e.g., paste a sample record)
- Upload clearer files (native PDF text, not scanned images)

### Duplicate records not merging

**Cause:** Blocking strategy missed them (different email, name variations)

**Fix:**
- Provide better context to agent (mentions how people appear in data)
- Verify match keys are correct (which fields define uniqueness?)
- Check **Provenance** in Graph tab to see original records

### LLM query timed out

**Cause:** Ollama is slow or overwhelmed

**Fix:**
- Wait 30–60 seconds, retry
- Check **Settings** → switch to Claude (if you have API key) for instant responses
- Reduce number of entities in graph (delete unused workspace)

## Best Practices

1. **Start with small data** — ingest 1 table or 10 documents first
2. **Provide crisp context** — "Customer accounts with names, emails, company IDs, deal amounts"
3. **Check provenance** — click entity in Graph tab → see original records
4. **Monitor costs** — Observability tab shows frontier LLM tokens used
5. **Iterate** — Reset and retry if discovery fails; context matters

## Next Steps

- [User Guide](USER_GUIDE.md) — Navigate the UI
- [Architecture](ARCHITECTURE.md) — Understand the pipeline stages
