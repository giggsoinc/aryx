---
name: auth-warden
description: "Closes G4: fail-open auth. Fixes the exception path in _bearer_ok, adds API-key middleware across all REST routers, keeps MCP bearer flow intact. Lane A — dispatch immediately, no dependencies."
allowed-tools: [Bash, Read, Write, Edit]
depends_on: []
files_owned: [src/aryx/api/main.py, src/aryx/api/security.py, tests/test_auth.py, docs/wiki/gaps/G4.md]
---

# auth-warden — Close G4 (Fail-Open Auth)

## Wiki Protocol
Read first: `docs/wiki/STATE.md`, `docs/wiki/sources/gap_map.md` §G4, `docs/wiki/gaps/G4.md`.
Write last: Work Log entry on G4.md + handoff block, committed WITH the code.

## Verified Baseline (do not re-derive)
- `src/aryx/api/main.py:43` — `_bearer_ok` returns `True` when token-store listing raises.
- `src/aryx/api/main.py:49` — outer exception handler also returns `True`. A Postgres outage silently disables MCP auth.
- `ARYX_MCP_AUTH_OPTIONAL` defaults to `"1"` (allow-all when no token presented).
- The 18 REST routers mounted in `main.py` have **no auth of any kind**.

## Implementation Prompt

You are hardening authentication in a FastAPI app. Three changes, in order:

**1. Fail-closed exception path (do this first, it ships alone if needed).**
In `_bearer_ok`, both exception returns become `False`. Log at ERROR, not WARNING — an auth check that cannot complete is an incident, not a curiosity. Preserve the documented allow-all behavior ONLY for the explicit cases: no token presented AND `ARYX_MCP_AUTH_OPTIONAL=1`, or token store reachable and zero unrevoked tokens exist. Reachability failure ≠ zero tokens.

**2. API-key middleware for the REST surface.**
Create `src/aryx/api/security.py`:
- A Starlette middleware reading `X-Aryx-Api-Key`, verified against the existing `McpTokenStore` (reuse it — same hashing, same table; do NOT invent a second token system).
- Env switch `ARYX_API_AUTH=off|optional|required`, default `optional` (warn-only headers) so existing deployments don't break on upgrade; document that `required` is the production setting.
- Exempt: `/health`, `/docs`, `/openapi.json`, and `/mcp/*` (MCP keeps its own bearer flow).
- On reject: 401 with `WWW-Authenticate`, body `{"detail": "missing or invalid api key"}` — no internals leaked.
- Constant-time comparison via the store's existing verify (confirm it hashes; if it compares plaintext, fix that here with `hmac.compare_digest` against sha256 digests).

**3. Tests — `tests/test_auth.py` (this gap raises non-RDF test count from zero):**
- `_bearer_ok` returns False when store raises (monkeypatch store to throw).
- Allow-all only under the two documented conditions.
- Middleware: 401 in `required` mode without key; 200 with valid key; exempt paths open; `optional` mode passes but sets a warning header.
- Use FastAPI TestClient; no live Postgres — monkeypatch the store.

**Constraints:** no new dependencies; keep every module under the repo's 150-line discipline (split security.py if needed); type hints + docstrings per house style (mirror `governor.py`).

## Acceptance Gates
- Full suite green including new test_auth.py (≥6 new tests).
- `grep -n "return True" src/aryx/api/main.py` shows zero hits inside exception handlers.
- Manual: kill Postgres, hit `/mcp` with any token → 401, log shows ERROR.

## Handoff
Write `docs/wiki/handoffs/auth-warden-<date>.md` per schema. `unblocks: []` (nothing depends on G4, but the program's demo-safety does). Flag in warnings: "ARYX_API_AUTH default is optional — flip to required before any shared deployment."
