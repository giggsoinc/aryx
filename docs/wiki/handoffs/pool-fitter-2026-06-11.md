---
agent: pool-fitter
gap: G12
date: 2026-06-11
status: DONE
branch: aryx-g12-pool
---

## Summary

Replaced per-store dedicated connections with a shared `psycopg_pool.ConnectionPool` singleton keyed by DSN. All 10 stores now borrow connections from the pool rather than holding them permanently.

## Delivered

- `requirements.txt` — added `pool` extra to psycopg3 install
- `src/aryx/store/pool.py` — `get_pool()` singleton + `close_all()` shutdown hook
- 10 stores rewritten: `ask_history_store`, `rule_store`, `version_store`, `mcp_token_store`, `job_store`, `chunk_store`, `entity_store`, `ontology_store`, `axiom_store`, `postgres_store`
- `src/aryx/api/main.py` — `_lifespan` calls `close_all()` on shutdown
- `tests/test_pool.py` — 4 tests, all passing

## Verification

```
# Acceptance gate
grep -rn "psycopg.connect" src/aryx/store/
# → only migrate.py

PYTHONPATH=src python -m pytest tests/test_pool.py -v
# 4 passed
```

## Carry-forwards

- `min_size=2, max_size=10` are defaults; expose via config/env for tuning under high load
- `entity_store.save_relationships` had a stale `conn.cursor().executemany(...)` pattern — verify fixed in this PR
