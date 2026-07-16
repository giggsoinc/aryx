---
name: raven-applog
description: Use when instrumenting application code or running the PR logging coverage gate.
  Checks that every required code path emits a valid raven_log() call.
  A PR below the coverage threshold is BLOCKED — logging is a non-negotiable gate.
allowed-tools: Read Write Edit Bash
---

# raven-applog — Application Log Coverage Gate

## Live project config
!`cat .raven/manifest.json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); lc=d.get('logging',{}); print('Project:', d.get('project'), '| Coverage threshold:', str(lc.get('coverage_threshold',100))+'%', '| Schema version:', lc.get('schema_version','1'), '| Exceptions:', lc.get('coverage_exceptions',[]))" 2>/dev/null || echo "Project: (manifest not found — run raven-init first)"`

---

## Run the coverage gate

Check the current PR diff for logging coverage (run this as part of the PR pipeline):

```bash
python3 raven-core/log-coverage-check.py --pr
```

Check staged files before committing:

```bash
python3 raven-core/log-coverage-check.py --staged
```

Check a single file directly:

```bash
python3 raven-core/log-coverage-check.py --file path/to/service.py
```

**Exit codes:** `0` = pass · `1` = BLOCKED (coverage below threshold) · `2` = scanner error (fail-open)

---

## What the gate checks

Every new or modified Python file in the diff is scanned for these mandatory path categories:

| Category | What it looks for | Fields required on log call |
|---|---|---|
| **Error handler** | `except` blocks | `level`, `error_code`, `criticality`, `trace_id` |
| **HTTP endpoint** | Functions with `@router.get/post/put/patch/delete` etc. | `level`, `trace_id`, `service` |
| **Critical business path** | Functions named `create_*`, `update_*`, `delete_*`, `process_*`, `pay_*`, `transfer_*`, etc. | `level`, `error_code`, `criticality`, `trace_id`, `span_id` |
| **External I/O** | Functions that call `httpx`, `requests`, `sqlalchemy`, `asyncpg`, `redis`, etc. | `level`, `trace_id`, `span_id`, `service` |

A path is **covered** when it contains a `raven_log()` call anywhere in its body.

---

## Adding coverage — step by step

**1. Dependency — enforced automatically:**

The gate checks `requirements.txt`, `pyproject.toml`, `setup.cfg`, and `setup.py` for `raven-logger`.
- **Found** → continues.
- **Not found** → auto-adds `raven-logger` to `requirements.txt` (creates the file if needed), then continues.

You never need to add it manually. After the gate runs, install it:
```bash
pip install raven-logger
```
Then import in your service:
```python
from raven_logger import raven_log, new_trace_id, new_span_id
```

**2. Error handlers (except blocks):**
```python
except Exception as e:
    raven_log(
        level="ERROR", criticality="P2", error_code="DB_CONN_TIMEOUT",
        message=str(e), trace_id=ctx.trace_id, span_id=ctx.span_id,
        service="payments-svc", env="prod", principal=ctx.user,
        project="atlas", context={"retries": retries},
    )
    raise
```

**3. HTTP endpoints — entry log:**
```python
@router.post("/payments/charge")
async def charge(request: ChargeRequest, ctx: RequestContext):
    raven_log(
        level="INFO", criticality="P3", error_code="",
        message="charge request received", trace_id=ctx.trace_id,
        span_id=ctx.span_id, service="payments-svc", env="prod",
        principal=ctx.user, project="atlas",
        context={"amount": request.amount, "currency": request.currency},
    )
    ...
```

**4. Critical business paths — success and failure logs:**
```python
async def process_payment(payload, ctx):
    raven_log(level="INFO", criticality="P3", error_code="",
              message="payment processing start", trace_id=ctx.trace_id,
              span_id=ctx.span_id, service="payments-svc", env="prod",
              principal=ctx.user, project="atlas")
    ...
```

**5. External I/O — around DB / HTTP calls:**
```python
raven_log(level="INFO", criticality="P3", error_code="",
          message="DB query: fetch account", trace_id=ctx.trace_id,
          span_id=ctx.span_id, service="payments-svc", env="prod",
          principal=ctx.user, project="atlas")
result = await db.fetch_one(query)
```

---

## Working example

A fully instrumented service lives at:

```bash
cat examples/payments_service.py
```

Run the coverage check against it to see a passing gate:

```bash
python3 raven-core/log-coverage-check.py --file examples/payments_service.py
```

Validate a record emitted by the SDK:

```bash
python3 raven-core/raven-log-validator.py --file examples/sample_records.jsonl
```

---

## PR gate outcome

| Result | Meaning |
|---|---|
| `✅ 100% (N/N paths)` | All mandatory paths covered — merge proceeds |
| `❌ 83% (5/6 paths)` | One or more uncovered — report posted to PR, **merge BLOCKED** |
| `⚠️  scanner error` | Parser failed (syntax error etc.) — fail-open, merge not blocked |

An override (rare) requires adding the path to `logging.coverage_exceptions` in `.raven/manifest.json` with a justification comment and explicit sign-off.

---

## Interactions

- Uses **raven-log** schema for field validation.
- Gate runs inside **pr-gate.py** alongside CVE scan and secret scan.
- Validated records flow to **Kafka bus** → **Log Analyzer** → triage/incident/KB.
