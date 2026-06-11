---
name: pool-fitter
description: "Closes G12: missing connection pooling. Adds psycopg_pool to the stack, creates a shared pool factory, rewires all 10 stores to borrow connections from the pool instead of opening a new psycopg.connect() each time. Lane D — no dependencies."
allowed-tools: [Bash, Read, Write, Edit]
depends_on: []
files_owned: [src/aryx/store/pool.py, src/aryx/store/__init__.py, tests/test_pool.py, docs/wiki/gaps/G12.md]
---

# pool-fitter — Close G12 (Connection Pooling)

## Wiki Protocol
Read first: `docs/wiki/STATE.md`, `docs/wiki/sources/gap_map.md` §G12, `docs/wiki/gaps/G12.md` (create if missing).
Write last: Work Log entry on G12.md + handoff block, committed WITH the code.

## Verified Baseline (do not re-derive)
- Every store in `src/aryx/store/*.py` calls `psycopg.connect(dsn, ...)` directly in `__init__`
- 10 stores × concurrent requests = connection explosion; Postgres `max_connections=100` exhausted at ~10 concurrent users
- `psycopg[binary]~=3.2` is already in `requirements.txt` — `psycopg_pool` ships in the same package as `psycopg[pool]`; just add it
- No pool or connection factory exists anywhere in the codebase

## Implementation Prompt

You are adding connection pooling to a FastAPI + Postgres platform. All stores currently open a raw `psycopg.connect()`. Your job: add a shared pool, rewire the stores to borrow from it, and add the pool extras to requirements.

**1. Add `psycopg[pool]` to `requirements.txt`**
Change the existing `psycopg[binary]~=3.2` line to `psycopg[binary,pool]~=3.2`. This activates `psycopg_pool.ConnectionPool` in the same installed package — no new dependency.

**2. New module `src/aryx/store/pool.py`**

```python
"""Shared psycopg3 connection pool — one per DSN, process-scoped."""
```

Implement:
- `get_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> ConnectionPool`
  - Returns a cached `psycopg_pool.ConnectionPool` for the given DSN.
  - Cache is a module-level `dict[str, ConnectionPool]` — one pool per DSN.
  - `min_size` / `max_size` configurable but sane defaults for a single-node deployment.
  - Pool uses `psycopg_pool.ConnectionPool(conninfo=dsn, min_size=min_size, max_size=max_size, open=True)`.
- `close_all() -> None` — closes every cached pool (for clean shutdown / tests).

**3. Rewire stores to use the pool**

For EACH of these stores (read them, patch them — do NOT rewrite wholesale):
- `entity_store.py`, `postgres_store.py`, `chunk_store.py`, `ontology_store.py`, `axiom_store.py` — these use `autocommit=False` (transaction mode)
- `mcp_token_store.py`, `version_store.py`, `ask_history_store.py`, `job_store.py`, `rule_store.py` — these use `autocommit=True`

Change pattern for each store:
```python
# Before
self._conn = psycopg.connect(dsn, autocommit=True)

# After  
self._pool = get_pool(dsn)
# In each method that uses self._conn:
with self._pool.connection() as conn:
    with conn.cursor() as cur:
        ...
```

Key rules:
- `ConnectionPool.connection()` is a context manager that returns a connection; on exit it returns the connection to the pool (no manual close needed).
- For transaction stores (`autocommit=False`): use `conn.transaction()` context manager inside the `with pool.connection()` block where commits were explicit. Remove manual `self._conn.commit()` calls — the context manager handles it.
- For autocommit stores: `pool.connection(autocommit=True)` is NOT how it works — instead use `with pool.connection() as conn: conn.autocommit = True`.
- Remove `self._conn` instance variable. Remove any `close()` methods that were just `self._conn.close()`.
- Add a `close()` method that calls `self._pool.close()` only if the store owns the pool (i.e. it called `get_pool`). Since pools are shared, `close()` should be a no-op for stores — only `close_all()` in `pool.py` closes the pool.

**4. FastAPI lifespan — `src/aryx/api/main.py`**

Add a lifespan event to close pools on shutdown:
```python
from contextlib import asynccontextmanager
from aryx.store.pool import close_all

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_all()

app = FastAPI(lifespan=lifespan, ...)
```

**5. Tests — `tests/test_pool.py`** (monkeypatched — no live Postgres):
- `get_pool` returns the same object for the same DSN (singleton behaviour)
- `get_pool` returns different objects for different DSNs
- `close_all` closes all cached pools and clears the cache
- Smoke test: store instantiation does not raise (mock `ConnectionPool.__init__` to a no-op)

**Constraints:**
- Only change the line in `requirements.txt`; do not add a second requirements file.
- Keep every module ≤150 lines. `pool.py` should be short (~40 lines).
- Type hints + docstrings per house style.
- Do NOT alter SQL queries or test fixtures — only the connection acquisition pattern changes.
- Run `PYTHONPATH=src python -m pytest tests/test_pool.py -v` before handoff.

## Acceptance Gates
- Full suite green including new test_pool.py (≥4 new tests).
- `grep -rn "psycopg.connect" src/aryx/store/` returns only `migrate.py` (the migration runner legitimately opens a raw connection — leave it alone).
- `python -c "from aryx.store.pool import get_pool, close_all; print('ok')"` runs without error.

## Handoff
Write `docs/wiki/handoffs/pool-fitter-<date>.md` per WIKI_SCHEMA.md.
`unblocks: []` (pooling is independent; all lanes benefit silently)
Warnings: "max_size=10 default — tune to Postgres max_connections minus headroom for migrations/admin. On a shared EC2 node with Postgres default 100: max_size=8 per process leaves room for 2 processes + admin."
