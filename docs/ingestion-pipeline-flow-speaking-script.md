# Speaking Script: Document Ingestion → Graph Pipeline

*Use this to walk your lead through the flow diagram. ~4-5 minutes if read straight through.*

---

## 1. One-line framing

"This is the path a file takes from the moment someone uploads it, to the moment its
entities show up as nodes in our graph — and there's one real gap in it I want to flag."

---

## 2. The entry point

"Everything comes in through two admin endpoints — `POST /admin/ingest/file` and
`POST /admin/docs/read` — which both hit `DocumentRouterConnector` in
[doc_router.py](../src/aryx/connectors/doc_router.py). It dispatches by file extension
using an `_EXT_MAP` table."

## 3. Stage 1 — Retrieval

"From there it fans out to a per-type connector: PDF, DOCX, PPTX, image, or markup.
All but one are working — `MarkupConnector` needs an allowlist fix before it's safe to
turn on. Each connector implements `extract_pages()`, which yields `(page_or_slide, text)`
pairs — that's the common contract every downstream stage relies on."

## 4. Stage 2 — Classification (proposed, doesn't exist yet)

"Right after extraction, the diagram shows a classification step — inferring the
document type from its actual content instead of trusting the file extension. That
box is orange because **it's proposed, not built**. Today we skip straight from
extraction to chunking."

## 5. Stage 3 — Chunking

"In [clean_text.py](../src/aryx/pipeline/clean_text.py): `_normalize()` does NFC
normalization, de-hyphenation, and blank-line collapsing, then a sliding window
(1000 chars, 100-char overlap) splits the page into `DocumentChunk` records —
each carrying `doc_id`, `chunk_index`, `page_slide`, and `text`."

## 6. Stage 4 — PII screening (the one hard gate)

"Every chunk goes through `screen_chunks()` in [pii.py](../src/aryx/pipeline/pii.py) —
Presidio-based, and **fail-closed**: if the PII scanner errors, the chunk doesn't pass.
This is the single choke point everything else sits downstream of."

## 7. The fork: two paths out of PII screening

"After screening, the pipeline splits two ways."

### 7a. Embeddings — currently a dead end

"One path runs `embed_chunks()` through a local Ollama model, storing vectors in
Postgres as `ChunkEmbedding` rows. But **nothing reads them back** — there's no
retrieval query hitting that table today. It's a fully-built pipeline with no
consumer yet."

### 7b. Entity extraction → graph — this is the live path

"The other path runs `extract_mentions()`, which produces a payload with the full
verbatim span text and a `record_id` shaped like `doc_id:chunk_index:i`. Those mentions
go through survivorship merge in
[survivor.py](../src/aryx/resolution/survivor.py), landing in `EntityStore` — and
critically, the **full span text typically survives** into the merged record, not
just a reference to it."

## 8. The graph write — and the actual problem

"`project_graph()` calls `add_entity()`, which writes those attributes — including
the full span — directly onto the FalkorDB node as properties. So today, every graph
node is carrying a duplicate copy of raw document text that already lives in Postgres.
That's the gray box on the diagram: **'the gap' — span text duplicated onto the
graph node.**"

*(Pause here — this is the part your lead needs to actually weigh in on.)*

## 9. The proposed fix

"The fix keeps the same `record_id` pointer — `doc_id:chunk_index` — but strips the
bulky span out of the node before it's projected. The FalkorDB node keeps name, type,
and key attributes plus that pointer; the full text stays in Postgres, dereferenced
on demand instead of duplicated. The Postgres side of this already exists and is live
— we're not adding new infrastructure, just changing what we write into the graph
node at `project_graph()` time."

## 10. The ask

"Three decisions I need from you:
1. Do we prioritize the graph-node fix now, or is duplicated span text tolerable for
   the current scale?
2. Is the classification stage (stage 2) worth building, or do we keep trusting file
   extensions?
3. Do we want to wire a reader onto the embeddings table, or shelve that path until
   there's an actual retrieval use case?"

---

### Reference: files mentioned above

| Stage | File |
|---|---|
| Routing | [src/aryx/connectors/doc_router.py](../src/aryx/connectors/doc_router.py) |
| Chunking | [src/aryx/pipeline/clean_text.py](../src/aryx/pipeline/clean_text.py) |
| PII screening | [src/aryx/pipeline/pii.py](../src/aryx/pipeline/pii.py) |
| Survivorship merge | [src/aryx/resolution/survivor.py](../src/aryx/resolution/survivor.py) |
