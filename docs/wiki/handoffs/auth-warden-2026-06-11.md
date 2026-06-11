---
agent: auth-warden
gap: G4
date: 2026-06-11
status: DONE
branch: aryx-g4-auth
---

## Summary

Implemented fail-closed auth for both the MCP bearer-token path and the REST API surface.

## Delivered

- `src/aryx/api/security.py` — `ApiKeyMiddleware` with `off|optional|required` modes, exempt paths, fail-closed `_verify_key`
- `src/aryx/api/main.py` — `_bearer_ok` exception handler fixed to `return False`; middleware + lifespan wired
- `tests/test_auth.py` — 11 tests (6 bearer-logic, 5 middleware), all passing without Docker

## Verification

```
PYTHONPATH=src python -m pytest tests/test_auth.py -v
# 11 passed
```

## Carry-forwards

- Integration tests (full app import + real token store) should run in Docker compose stack
- `store.close()` call in `_bearer_ok` will conflict when G12 (pool) merges — remove it then
