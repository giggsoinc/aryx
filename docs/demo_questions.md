 - Ontology: A map of what things are and how they relate — not just words, but typed facts (Acme Corp is an Organization, it SUPPLIES Globex).
  - Why important: Lets you query by meaning across any source — one question traverses CRM + support + contracts simultaneously.
  - RAG vs Ontology: RAG finds the most similar text passage; ontology finds the most connected fact. RAG says "here's a paragraph mentioning Acme" — ontology says "Acme supplies Globex, 
  who partners with Umbrella, who competes with Acme".
  
# Aryx Demo — 5 Questions: Without vs With Ontology

**Live data:** 5 companies · 4 relationships · 1 CRM source  
**Ask these in Claude Desktop (aryx MCP connected)**

---

## Q1 — Who supplies Acme Corp?

### Without Ontology (raw CRM table)
```sql
SELECT * FROM demo_customers WHERE full_name = 'Acme Corp';
```
**Result:** One row. `full_name`, `email`, `country`, `signed_up`.  
No supplier information exists in the table. The question **cannot be answered**.

### With Ontology (ask Claude)
> *"Who supplies Acme Corp?"*

Claude calls `search_entities` → `get_neighbors` and answers:  
**"Globex LLC supplies Acme Corp"** — a relationship surfaced from the graph that never existed as a column in the source data.

---

## Q2 — Which company was acquired and by whom?

### Without Ontology (raw CRM table)
```sql
SELECT * FROM demo_customers;
```
**Result:** 5 rows of customer data. Acquisition status is not a field.  
The question **cannot be answered** from the source.

### With Ontology (ask Claude)
> *"Which company was acquired and who acquired them?"*

Claude calls `search_entities` → `get_neighbors` and answers:  
**"Initech was acquired by Stark Industries"** — a fact that was resolved from the graph, not the CRM.

---

## Q3 — Map all relationships between these companies

### Without Ontology (raw CRM table)
```sql
SELECT full_name, country, email FROM demo_customers ORDER BY full_name;
```
**Result:** A flat list. No connections between companies are visible.  
The question **cannot be answered**.

### With Ontology (ask Claude)
> *"Show me all the relationships between the companies in the system"*

Claude calls `search_entities` → `get_neighbors` for each entity and returns:  
- Globex LLC **SUPPLIES** Acme Corp  
- Stark Industries **ACQUIRED** Initech  
- Umbrella Co **PARTNERS WITH** Globex LLC  
- Acme Corp **COMPETES WITH** Umbrella Co  

A full relationship map from a single question.

---

## Q4 — What do we know about Umbrella Co?

### Without Ontology (raw CRM table)
```sql
SELECT * FROM demo_customers WHERE full_name = 'Umbrella Co';
```
**Result:** `country: GB`, `email: finance@umbrella.example`, `signed_up: 2024-06-11`.  
Isolated record — no context, no connections.

### With Ontology (ask Claude)
> *"Tell me everything we know about Umbrella Co"*

Claude calls `get_entity` → `get_neighbors` → `get_provenance` and answers:  
**"Umbrella Co is a UK-based customer (onboarded June 2024). They partner with Globex LLC and compete with Acme Corp. This record was sourced from the PostgreSQL CRM (demo_customers)."**  
One question, three tool calls, full picture.

---

## Q5 — Which companies are most connected?

### Without Ontology (raw CRM table)
```sql
SELECT full_name, country FROM demo_customers;
```
**Result:** 5 flat rows. No way to rank by connectivity — relationships don't exist in the table.  
The question **cannot be answered**.

### With Ontology (ask Claude)
> *"Which company has the most connections in the system?"*

Claude calls `search_entities` → `get_neighbors` for all entities and answers:  
**"Acme Corp and Globex LLC are the most connected — each appears in two relationships. Acme competes with Umbrella Co and is supplied by Globex. Globex supplies Acme and partners with Umbrella Co."**

---

## The Point

| | Without Ontology | With Ontology |
|---|---|---|
| Data shape | Flat rows, siloed columns | Connected graph |
| Query type | SQL — you must know what to ask | Natural language — Claude finds the path |
| Relationships | Not captured | First-class citizens |
| New source added | New table, new schema | Same graph, same questions |
| Answer to "who supplies Acme?" | ❌ Not possible | ✅ Instant |

> **"The CRM told us Acme Corp exists. The ontology tells us Acme Corp matters — and why."**
