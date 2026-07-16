---
name: raven-log
description: Use when defining, validating, or referencing the canonical raven-log contract.
  Provides the field schema, criticality P1-P4 guide, and record validation.
  Run /raven-log validate <json> to check any log record.
allowed-tools: Read Bash
---

# raven-log — Canonical Log Contract

## Live project context
!`cat .raven/manifest.json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); lc=d.get('logging',{}); print('Project:', d.get('project'), '| Schema version:', lc.get('schema_version','1'), '| DLQ:', lc.get('dlq_path','.raven/dlq/'))" 2>/dev/null || echo "Project: (manifest not found — run raven-init first)"`

---

## Record schema

Every emitter — app, cloud, or security — must produce this exact shape:

```json
{
  "schema_version": "1",
  "timestamp":      "ISO-8601",
  "level":          "ERROR|WARN|INFO|DEBUG",
  "criticality":    "P1|P2|P3|P4",
  "service":        "<registered service name>",
  "env":            "prod|staging|dev",
  "trace_id":       "<propagated or generated at boundary>",
  "span_id":        "<span within trace>",
  "principal":      "<@giggso.com email or service account>",
  "error_code":     "<NAMESPACE_ERROR_NAME>",
  "message":        "<human-readable description>",
  "context":        {},
  "sample_payload": "<PII-redacted payload excerpt>",
  "project":        "<GREaaS project tag>"
}
```

**All fields are required.** `error_code` and `criticality` must be non-empty on every ERROR or WARN record.

---

## Criticality guide

| P | Business meaning | Example |
|---|---|---|
| P1 | Service-down / data-loss / security-critical | Payments API unreachable; DB data corruption |
| P2 | Major degradation; or WARN repeated past threshold | 50% error rate; connection pool exhausted |
| P3 | Minor / contained; single-user impact | A single user's request failed; retry succeeded |
| P4 | Informational / cosmetic | Config loaded; cache warm; background job started |

**Rule:** assign criticality at the call site. Never leave it to downstream inference. A WARN you know will repeat is P2, not P3.

---

## Schema versioning

| Version | Status |
|---|---|
| Current (1) | Accepted |
| N-1 (0) | Accepted — rolling upgrade grace period |
| N-2 and below | Rejected to DLQ |

Add `"schema_version": "1"` to every emitted record. When a new version ships, emitters have one release cycle to upgrade before N-2 rejection kicks in.

---

## Validate a record

Check any JSON record against the schema:

```bash
python3 raven-core/raven-log-validator.py --record '{"schema_version":"1","timestamp":"2026-06-22T10:00:00Z","level":"ERROR","criticality":"P2","service":"payments-svc","env":"prod","trace_id":"abc-123","span_id":"span-1","principal":"m.abbasi@giggso.com","error_code":"DB_CONN_TIMEOUT","message":"DB connection timed out","context":{"retries":3},"sample_payload":"","project":"atlas"}'
```

Validate a JSONL file (batch):

```bash
python3 raven-core/raven-log-validator.py --file records.jsonl
```

---

## Interactions

- **raven-applog** enforces that this schema is emitted at every required code path.
- **raven-triage** fingerprints records using `error_code` + `service` + normalized `message`.
- **Log Analyzer** maps every record to OCSF and routes to the KB or incident workflow.
- Malformed records → **DLQ** (never block the app thread; never silently drop).
