"""Multi-table SQL ingest: shared by /admin/ingest/multi and datasource ingest.

``run_multi`` ingests a list of confirmed tables as one job and links them by
the FK ``edges``. ``map_and_ingest`` is the datasource-ingest variant: it runs
the (slow, LLM-backed) schema mapping inside the background job first, so the
HTTP request never waits on the model.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.config import get_settings
from aryx.connectors.sql_source import SqlConnector, sample_colvals
from aryx.pipeline.orchestrate import run_pipeline
from aryx.pipeline.schema_agent import discover_mappings
from aryx.resolution.field_shape import resolve_match_keys
from aryx.store.job_store import JobStore

logger = logging.getLogger(__name__)


def should_skip_resolution(pk: list[str], match_keys: list[str],
                           transactional: bool) -> bool:
    """Decide whether a table's rows can bypass entity resolution.

    Skip only when each row is known to be its own real-world thing:

    * ``resolve_match_keys`` judged the type transactional (a genuine
      per-row identifier on a fact type);
    * a **composite** primary key — line / fact tables such as
      ``po_number + line_number``;
    * the match keys *are* the primary key, so resolution would only ever
      compare unique values.

    A single surrogate PK (``id``) next to free-text match keys still
    resolves: it makes rows distinct, not the companies / suppliers in them.
    """
    if transactional or len(pk) > 1:
        return True
    return bool(pk) and bool(match_keys) and set(match_keys) <= set(pk)


def run_multi(url: str, tables: list[dict], edges: list[dict], job_id: str,
              workspace_id: int = 1) -> None:
    """Ingest every confirmed table, then link them by ``edges``."""
    from aryx.api.admin_api import _local_broker  # lazy: api imports pipeline
    settings = get_settings()
    jobs = JobStore(settings.rdb_dsn)
    broker = _local_broker()
    try:
        total = len(tables)
        for i, t in enumerate(tables):
            pct = int(10 + i * 80 / max(total, 1))
            jobs.update_stage(job_id, f"Table {i + 1}/{total}", pct,
                              f"Ingesting {t['table']}")
            pk = list(t.get("pk") or [])
            keys = t.get("match_keys") or ["id"]
            # Record identity = the full primary key when known, so composite
            # keys (po_number + line_number) don't collapse onto one column.
            record_key = pk or [keys[0]]
            colvals = sample_colvals(url, t["table"])
            keys, transactional = resolve_match_keys(keys, colvals)
            run_pipeline(
                connector=SqlConnector(url, t["table"], record_key, system="rdb"),
                dsn=settings.rdb_dsn, system="rdb", dataset=t["table"],
                ontology_type=t["ontology_type"], match_keys=keys,
                broker=broker,
                workspace_id=workspace_id,
                fk_links=edges if i == total - 1 else [],
                skip_resolution=should_skip_resolution(pk, keys, transactional),
            )
        jobs.finish(job_id, run_id=None, status="complete")
    except Exception as exc:  # noqa: BLE001 — job row carries the failure
        logger.warning("multi ingest failed job=%s: %s", job_id, exc)
        jobs.finish(job_id, run_id=None, status="failed", error=str(exc))
    finally:
        jobs.close()


def map_tables(schema: list[dict[str, Any]], context: str
               ) -> tuple[list[dict], list[dict]]:
    """Propose the ontology mapping and attach each table's full PK."""
    mapping = discover_mappings(schema, context)
    pk_by_table = {t["table"]: list(t.get("pk") or []) for t in schema}
    tables = [{**t, "pk": pk_by_table[t["table"]]}
              for t in mapping.get("tables", []) if t.get("table") in pk_by_table]
    return tables, list(mapping.get("edges", []))


def map_and_ingest(url: str, schema: list[dict[str, Any]], context: str,
                   job_id: str, workspace_id: int) -> None:
    """Background: map the schema with the business context, then ingest."""
    jobs = JobStore(get_settings().rdb_dsn)
    try:
        jobs.update_stage(job_id, "Mapping", 5,
                          f"Mapping {len(schema)} table(s) to the ontology")
        tables, edges = map_tables(schema, context)
        if not tables:
            jobs.finish(job_id, run_id=None, status="failed",
                        error="None of the tables could be mapped for ingest.")
            return
    except Exception as exc:  # noqa: BLE001 — job row carries the failure
        logger.warning("datasource mapping failed job=%s: %s", job_id, exc)
        jobs.finish(job_id, run_id=None, status="failed",
                    error=f"Mapping failed: {exc}")
        return
    finally:
        jobs.close()
    logger.info("datasource mapping done job=%s tables=%d edges=%d",
                job_id, len(tables), len(edges))
    run_multi(url, tables, edges, job_id, workspace_id)
