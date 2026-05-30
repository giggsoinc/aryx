 - Ontology: A map of what things are and how they relate — not just words, but typed facts (Acme Corp is an Organization, it SUPPLIES Globex).
  - Why important: Lets you query by meaning across any source — one question traverses CRM + support + contracts simultaneously.
  - RAG vs Ontology: RAG finds the most similar text passage; ontology finds the most connected fact. RAG says "here's a paragraph mentioning Acme" — ontology says "Acme supplies Globex, 
  who partners with Umbrella, who competes with Acme".
  
# Aryx Support Demo — Two Sources, One Graph

**Live data:**
- Source 1: `demo_customers` (CRM) — 5 companies
- Source 2: `demo_support_tickets` (Support) — 7 tickets
- Graph: 12 entities · 11 relationships · 2 sources resolved together

---

## Q1 — Which companies have open support tickets right now?

### Without Ontology
```sql
-- CRM query — knows nothing about tickets
SELECT full_name FROM demo_customers;

-- Support query — knows nothing about CRM relationships
SELECT customer_name, ticket_ref, status
FROM demo_support_tickets WHERE status = 'OPEN';
```
**Result:** Two separate queries, two separate tables. No connection between them.  
You manually match `customer_name` to `full_name` in your head.

### With Ontology (ask Claude)
> *"Which companies have open support tickets?"*

Claude calls `search_entities(type=SupportTicket)` → filters by name containing `OPEN` → `get_neighbors` in reverse.  
**"Acme Corp has T-001 (API integration failing) open. Umbrella Co has T-005 (Permission denied on API) open. Initech has T-006 (Onboarding stuck) open."**  
Two sources. One answer.

---

## Q2 — Which company needs the most urgent attention?

### Without Ontology
```sql
SELECT customer_name, ticket_ref, severity, status
FROM demo_support_tickets
WHERE severity = 'HIGH'
ORDER BY created_at;
```
**Result:** Raw rows. You don't know if these companies also compete with each other, or if one is a supplier to another — that context lives in a different table.

### With Ontology (ask Claude)
> *"Which company needs the most urgent attention and what else do we know about them?"*

Claude calls `search_entities` → `get_neighbors` → cross-references company relationships.  
**"Umbrella Co has two HIGH-severity tickets — one ESCALATED, one OPEN. They also partner with Globex LLC and compete with Acme Corp, both of whom have their own active tickets. This cluster warrants immediate review."**

---

## Q3 — Is there a pattern between competing companies and their support issues?

### Without Ontology
Impossible with SQL alone — relationships between companies don't exist in either table.

### With Ontology (ask Claude)
> *"Do any competing companies share similar support issues?"*

Claude traverses: `COMPETES_WITH` edges → checks each company's `HAS_TICKET` edges.  
**"Acme Corp and Umbrella Co are competitors. Both have API-related tickets open — T-001 (API integration failing) and T-005 (Permission denied on API). This may indicate a shared integration point worth investigating."**

---

## Q4 — What's the full picture on Umbrella Co?

### Without Ontology
```sql
-- Query 1: CRM
SELECT * FROM demo_customers WHERE full_name = 'Umbrella Co';
-- Query 2: Support
SELECT * FROM demo_support_tickets WHERE customer_name = 'Umbrella Co';
```
**Result:** Two queries, two result sets, manual correlation.  
No visibility into their market relationships.

### With Ontology (ask Claude)
> *"Give me the full picture on Umbrella Co"*

Claude calls `get_entity` → `get_neighbors` → `get_provenance`.  
**"Umbrella Co is a UK-based customer (onboarded June 2024, finance@umbrella.example). They have 2 active support tickets — one ESCALATED (Data export timeout, HIGH). They partner with Globex LLC and compete with Acme Corp. Data sourced from CRM and support system."**  
One question. Complete picture.

---

## Q5 — Which supplier has the cleanest support record?

### Without Ontology
`SUPPLIES` is not a column. This query cannot be written in SQL against these tables.

### With Ontology (ask Claude)
> *"Which of our suppliers has the cleanest support record?"*

Claude finds `SUPPLIES` edges → checks each supplier's `HAS_TICKET` edges.  
**"Globex LLC supplies Acme Corp and has only one ticket — T-003, which is already RESOLVED. They have the cleanest support record of any company with a supply relationship."**

---

## The Point — Two Sources, Zero Joins

| | Without Ontology | With Ontology |
|---|---|---|
| CRM + Support together | Manual JOIN or copy-paste | Same graph, automatic |
| "Which supplier has issues?" | Not possible | Instant |
| Context across sources | You provide it | Graph provides it |
| New source added | New schema, new queries | `aryx run`, same questions |

> **"We didn't join two tables. We resolved two sources into one truth — and asked questions that neither source could answer alone."**
