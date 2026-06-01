# RDF Export & Downstream Integration

## Overview

Aryx exports knowledge graphs as RDF (Resource Description Framework) / OWL (Web Ontology Language) for integration with semantic web tools, SPARQL endpoints, data lakes, and LLM pipelines. This guide covers API endpoints, consumption patterns, and tool-specific integration examples.

**Prerequisite:** The ontology interchange plugin must be enabled in **Settings → Ontology interchange** (toggle on, pick the formats to expose). Until enabled, the export/import endpoints return `403`.

---

## API Reference

All routes are served by the Aryx API (default `http://localhost:8088`). The
active workspace is selected with the `workspace_id` query parameter (defaults
to `1`). Formats are RDF serialisations — there is no separate `serialization`
parameter.

### Supported formats

| `format` value | Serialisation | Media type | File extension |
|---|---|---|---|
| `turtle` | Turtle | `text/turtle` | `.ttl` |
| `json-ld` | JSON-LD | `application/ld+json` | `.jsonld` |
| `xml` | RDF/XML | `application/rdf+xml` | `.rdf` |
| `n-triples` | N-Triples | `application/n-triples` | `.nt` |

### Export the graph

```
GET /ontology/export?workspace_id={id}&format={format}
```

Returns the serialised graph as a downloadable file (`Content-Disposition:
attachment`). `403` if the plugin is disabled or the format is not enabled in
Settings.

**Response:**

```
HTTP 200 OK
Content-Type: text/turtle; charset=utf-8
Content-Disposition: attachment; filename="aryx_ws1.ttl"

@prefix aryx: <https://aryx.local/ontology#> .
@prefix ent:  <https://aryx.local/entity/> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
...
```

### Import an ontology

```
POST /ontology/import
Content-Type: application/json

{ "workspace_id": 1, "content": "<RDF document text>", "format": "turtle", "filename": "schema.ttl" }
```

`format` may be omitted (or `""`) to auto-detect from `filename`. Parsed
`owl:Class` / `rdfs:Class` declarations are seeded as **proposed** ontology
types (`source = "owl-import"`) that still pass the human review gate.

**Response:**

```json
{ "imported": 2, "types": ["Invoice", "Customer"], "format": "turtle",
  "message": "imported as 'proposed' — approve them in the ontology review gate" }
```

### Config & format discovery

```
GET  /ontology/config      -> { enabled, formats, base_uri, include_provenance, available }
POST /ontology/config      -> update any of the above (Settings panel uses this)
GET  /ontology/formats     -> [ { name, media_type, extension }, ... ]
```

---

## Consumption Patterns

### 1. Direct HTTP/REST (curl, Python requests)

**Fetch and save Turtle to a file:**

```bash
curl "http://localhost:8088/ontology/export?workspace_id=1&format=turtle" \
  > knowledge_graph.ttl
```

**Python:**

```python
import requests

workspace_id = 1

response = requests.get(
    "http://localhost:8088/ontology/export",
    params={"workspace_id": workspace_id, "format": "turtle"}
)

with open("graph.ttl", "wb") as f:
    f.write(response.content)

print(f"Exported {len(response.content)} bytes")
```

**Key considerations:**
- Response can be 10–100+ MB for large graphs
- Gzip client-side for slow networks: `curl ... | gzip > graph.ttl.gz`
- Streaming recommended for >50 MB: `stream=True` in requests

---

### 2. Semantic Web Tools (Protégé, TopBraid)

#### Protégé (Free, open-source ontology editor)

**Steps:**

1. Export from Aryx: `curl ... > aryx_graph.ttl`
2. Open Protégé → File → Open → aryx_graph.ttl
3. Visualize ontology, edit class hierarchy, add axioms
4. Run reasoner (HermiT, Pellet) to infer class membership
5. Export back to Aryx (optional): File → Export as RDF/XML → upload to Aryx

**Example workflow:**

```bash
# Export
curl "http://localhost:8088/ontology/export?workspace_id=1&format=turtle" \
  > customer_graph.ttl

# Edit in Protégé, then re-import to Aryx:
curl -X POST "http://localhost:8088/ontology/import" \
  -H "Content-Type: application/json" \
  -d "{\"workspace_id\": 1, \"format\": \"xml\", \"content\": $(jq -Rs . customer_graph.rdf)}"
```

#### TopBraid Composer (Commercial, visual ontology design)

- Import TTL files directly
- Design SHACL shapes for validation
- Generate documentation
- Export back to Aryx

---

### 3. SPARQL Endpoints

Query the exported RDF in a triple store (Apache Jena, Virtuoso, AllegroGraph).

**Setup (Docker example):**

```bash
# Start Apache Jena Fuseki triple store
docker run -d -p 3030:3030 \
  -e FUSEKI_DATASET_1=aryx \
  -v ./data:/fuseki/data \
  stain/jena-fuseki

# Load RDF from Aryx
curl -X POST \
  "http://localhost:3030/aryx/data?graph=http://aryx.local/ws_1" \
  -H "Content-Type: text/turtle" \
  -d @knowledge_graph.ttl
```

**SPARQL query example:**

```sparql
PREFIX schema: <http://schema.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?name ?company
WHERE {
  ?person rdf:type schema:Person ;
          schema:name ?name ;
          schema:worksFor ?company .
  ?company schema:name "Acme Corp" .
}
```

**Use cases:**
- Ad-hoc queries on exported graphs
- Data lineage / provenance tracking
- Federated queries (Aryx + other RDF sources)
- Complex reasoning over merged ontologies

---

### 4. Python SDK (Wrapper)

**Client library (example):**

```python
import requests
from rdflib import Graph, Namespace, RDF

# Fetch Turtle straight from the export endpoint
resp = requests.get(
    "http://localhost:8088/ontology/export",
    params={"workspace_id": 1, "format": "turtle"},
)
graph = Graph()
graph.parse(data=resp.text, format="turtle")

# Aryx mints classes under <base_uri>ontology# (default https://aryx.local/)
ARYX = Namespace("https://aryx.local/ontology#")

# Find all Company individuals
for company in graph.subjects(RDF.type, ARYX.Company):
    print(graph.value(company, ARYX.name))

# Save locally
graph.serialize("merged_graph.ttl", format="turtle")
```

**Install:**

```bash
pip install requests rdflib
```

---

### 5. ETL Pipelines (Airflow, Dagster)

**Airflow DAG example:**

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime
import requests
import json

def export_rdf_from_aryx(**context):
    """Fetch RDF from Aryx."""
    workspace_id = 1

    response = requests.get(
        "http://aryx:8088/ontology/export",
        params={"workspace_id": workspace_id, "format": "json-ld"},
    )

    with open("/tmp/aryx_export.jsonld", "w") as f:
        f.write(response.text)

    return {"bytes": len(response.content), "status": "success"}

def load_to_warehouse(**context):
    """Load RDF to Snowflake / BigQuery."""
    # Parse JSONLD, transform to tabular format, insert to warehouse
    import json
    from rdflib import Graph
    
    g = Graph()
    g.parse("/tmp/aryx_export.jsonld", format="json-ld")
    
    # Flatten RDF to rows: subject, predicate, object
    rows = []
    for s, p, o in g:
        rows.append({
            "subject": str(s),
            "predicate": str(p),
            "object": str(o),
            "export_date": datetime.now().isoformat()
        })
    
    # Insert to Snowflake
    # from snowflake.connector import connect
    # conn.cursor().executemany("INSERT INTO rdf_data VALUES (%s, %s, %s, %s)", rows)

dag = DAG(
    "aryx_rdf_export_daily",
    start_date=datetime(2026, 1, 1),
    schedule_interval="@daily"
)

export_task = PythonOperator(
    task_id="export_rdf",
    python_callable=export_rdf_from_aryx,
    dag=dag
)

load_task = PythonOperator(
    task_id="load_warehouse",
    python_callable=load_to_warehouse,
    dag=dag
)

export_task >> load_task
```

---

### 6. Knowledge Graph Federation

**Merge Aryx RDF with Wikidata/DBpedia:**

```python
from rdflib import Graph, Namespace
from rdflib.tools.rdf2dot import rdf2dot

# Load Aryx RDF
aryx_graph = Graph()
aryx_graph.parse("aryx_export.ttl", format="turtle")

# Load Wikidata (via SPARQL endpoint)
from rdflib.plugins.stores.sparqlstore import SPARQLStore

wikidata = Graph(store=SPARQLStore(
    endpoint="https://query.wikidata.org/sparql"
))

# Query Wikidata for external company data
query = """
SELECT ?company ?label
WHERE {
  ?company wdt:P31 wd:Q783794 .  # instance of company
  ?company rdfs:label ?label . FILTER(LANG(?label) = "en")
}
LIMIT 1000
"""

results = wikidata.query(query)

# Merge: add Wikidata entities to Aryx graph
for company, label in results:
    aryx_graph.add((company, RDFS.label, label))

# Export merged graph
aryx_graph.serialize("federated_graph.ttl", format="turtle")
```

**Use cases:**
- Enrich customer/company data with Wikidata facts
- Link Aryx entities to DBpedia URIs
- Federated reasoning across organizational + public knowledge bases

---

### 7. RAG (LLM Context Injection)

**Convert RDF to natural language facts for LLM prompt:**

```python
from rdflib import Graph, Namespace
from anthropic import Anthropic

client = Anthropic()

# Load RDF
graph = Graph()
graph.parse("customer_graph.ttl", format="turtle")

# Extract facts as natural language
facts = []
for s, p, o in graph:
    facts.append(f"{s.split('/')[-1]} {p.split('/')[-1]} {o}")

# Inject into Claude prompt
context = "\n".join(facts[:100])  # Limit to avoid token overflow

response = client.messages.create(
    model="claude-opus-4-1",
    max_tokens=1024,
    messages=[
        {
            "role": "user",
            "content": f"""
Based on this customer knowledge graph:

{context}

Answer: Which customers have the highest deal values?
"""
        }
    ]
)

print(response.content[0].text)
```

**Benefits:**
- Ground LLM responses in actual data (avoid hallucinations)
- Use Aryx as a retrieval layer for RAG systems
- Link reasoning back to source records via provenance

---

### 8. Compliance & Audit

**Export and validate data lineage:**

```python
from rdflib import Graph, Namespace
from rdflib.tools.rdf2dot import rdf2dot

PROV = Namespace("http://www.w3.org/ns/prov#")

graph = Graph()
graph.parse("aryx_export.ttl", format="turtle")

# Query provenance (where did this entity come from?)
query = """
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?entity ?source ?timestamp
WHERE {
  ?entity prov:wasGeneratedBy ?activity .
  ?activity prov:wasInformedBy ?source ;
            prov:atTime ?timestamp .
}
"""

for entity, source, timestamp in graph.query(query):
    print(f"{entity} <- {source} @ {timestamp}")
    # Log to audit system for compliance reporting
```

**Requirements satisfied:**
- GDPR: track data origin and transformations
- SOX: audit trail of all entity merges
- ISO 8601: timestamp of every operation

---

### 9. Data Marketplace (Open Dataset)

**Publish as open dataset (Zenodo, Figshare):**

```bash
# Export Turtle, then gzip locally
curl "http://localhost:8088/ontology/export?workspace_id=1&format=turtle" \
  | gzip > aryx_customer_graph.ttl.gz

# Upload to Zenodo (requires account)
curl -X POST \
  -H "Authorization: Bearer $ZENODO_TOKEN" \
  -F "file=@aryx_customer_graph.ttl.gz" \
  https://zenodo.org/api/deposit/depositions/$DEPOSITION_ID/files

# Receive DOI: https://zenodo.org/record/12345678
```

**Metadata file (for discovery):**

```json
{
  "title": "Aryx Customer Knowledge Graph (Q2 2026)",
  "description": "Deduplicated customer records from CRM, support, and product systems",
  "format": "RDF/Turtle",
  "license": "CC-BY-4.0",
  "keywords": ["customer-data", "knowledge-graph", "deduplication"],
  "entities": 50000,
  "relationships": 125000,
  "export_date": "2026-05-31"
}
```

---

### 10. Custom Dashboards (D3.js, Cytoscape)

**Parse and visualize RDF in web UI:**

```javascript
// Fetch JSON-LD from Aryx
fetch('http://localhost:8088/ontology/export?workspace_id=1&format=json-ld')
.then(r => r.json())
.then(jsonld => {
  // Convert JSON-LD to node/edge format
  const nodes = [];
  const edges = [];
  
  jsonld['@graph'].forEach(entity => {
    nodes.push({
      id: entity['@id'],
      label: entity['http://schema.org/name']?.[0]['@value'],
      type: entity['@type']?.[0]
    });
    
    Object.entries(entity).forEach(([key, values]) => {
      if (key.includes('http') && Array.isArray(values)) {
        values.forEach(v => {
          if (v['@id']) {
            edges.push({
              source: entity['@id'],
              target: v['@id'],
              label: key.split('/').pop()
            });
          }
        });
      }
    });
  });
  
  // Render with Cytoscape
  cy = cytoscape({
    container: document.getElementById('cy'),
    elements: [
      ...nodes.map(n => ({ data: n })),
      ...edges.map(e => ({ data: e }))
    ],
    style: [...] // standard Cytoscape stylesheet
  });
});
```

---

## Response Formats

### Turtle (TTL) — Human-readable, compact

```turtle
@prefix schema: <http://schema.org/> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .

<http://aryx.local/entity/person_1> a schema:Person ;
    schema:name "John Smith" ;
    schema:email "john@example.com" ;
    schema:worksFor <http://aryx.local/entity/company_5> .

<http://aryx.local/entity/company_5> a schema:Company ;
    schema:name "Acme Corp" ;
    schema:url "https://acme.com" .
```

### JSON-LD — Web-friendly, embeddable

```json
{
  "@context": "http://schema.org/",
  "@graph": [
    {
      "@id": "http://aryx.local/entity/person_1",
      "@type": "Person",
      "name": "John Smith",
      "email": "john@example.com",
      "worksFor": {
        "@id": "http://aryx.local/entity/company_5"
      }
    },
    {
      "@id": "http://aryx.local/entity/company_5",
      "@type": "Company",
      "name": "Acme Corp",
      "url": "https://acme.com"
    }
  ]
}
```

### RDF/XML — Standard, interchange format

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:schema="http://schema.org/">
  <rdf:Description rdf:about="http://aryx.local/entity/person_1">
    <rdf:type rdf:resource="http://schema.org/Person"/>
    <schema:name>John Smith</schema:name>
    <schema:email>john@example.com</schema:email>
    <schema:worksFor rdf:resource="http://aryx.local/entity/company_5"/>
  </rdf:Description>
</rdf:RDF>
```

### N-Triples — Line-based, streaming-friendly

```
<http://aryx.local/entity/person_1> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://schema.org/Person> .
<http://aryx.local/entity/person_1> <http://schema.org/name> "John Smith" .
<http://aryx.local/entity/person_1> <http://schema.org/email> "john@example.com" .
```

---

## Size & Performance

| Graph Size | Entities | Relationships | TTL File | Compressed | Export Time |
|---|---|---|---|---|---|
| Small | 1K | 5K | 2 MB | 400 KB | <1 sec |
| Medium | 50K | 250K | 100 MB | 15 MB | 5–10 sec |
| Large | 1M | 5M | 2 GB | 300 MB | 30–60 sec |
| XL | 10M+ | 50M+ | 20+ GB | 3+ GB | 2–5 min |

**Optimization tips:**
- Gzip on the client for large files: `curl ... | gzip > graph.ttl.gz`
- Stream large exports to disk, don't load in memory
- Use N-Triples for streaming (one statement per line)
- Keep workspaces focused — one project per workspace keeps each export small

---

## Error Handling

**Common errors:**

| Error | Cause | Fix |
|---|---|---|
| `403 Forbidden` | Plugin disabled, or format not enabled | Enable in Settings → Ontology interchange |
| `400 Bad Request` | Unsupported format / unparseable import | Use turtle, json-ld, xml, or n-triples |
| `500 Internal Error` | Store or serialization fault (rare) | Check API logs, retry; report to support |

**Retry strategy:**

```python
import time
import requests

def export_with_retry(workspace_id=1, fmt="turtle"):
    for attempt in range(3):
        try:
            response = requests.get(
                "http://localhost:8088/ontology/export",
                params={"workspace_id": workspace_id, "format": fmt},
                timeout=300,  # 5 min for large exports
            )
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException:
            if attempt < 2:
                time.sleep(2 ** attempt)  # exponential backoff
            else:
                raise
```

---

## Best Practices

1. **Network exposure** — The API has no auth layer yet; keep `:8088` on a private network or front it with a reverse proxy
2. **Caching** — Cache RDF exports locally; re-fetch only after new ingest jobs
3. **Compression** — Gzip large exports client-side: `curl ... | gzip > graph.ttl.gz`
4. **Validation** — Validate Turtle syntax after export: `riot --check graph.ttl` (Apache Jena)
5. **Versioning** — Include workspace ID + date in the filename: `aryx_ws1_2026-05-31.ttl`
6. **Review imports** — Imported types land as *proposed*; approve them in the ontology review gate before relying on them
7. **Backup** — Store exports in S3 / GCS for compliance archival
8. **Base URI** — Set a stable, owned base URI in Settings so exported IRIs are dereferenceable

---

## Next Steps

- [Architecture](ARCHITECTURE.md) — Understand how RDF export fits into Aryx
- [Ingestion Guide](INGESTION_GUIDE.md) — Import external RDF/OWL schemas
- [User Guide](USER_GUIDE.md) — Enable export in Settings
