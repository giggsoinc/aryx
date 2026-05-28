"""CLI for the end-to-end pipeline (Increment 7).

Usage:
    python -m aryx.cli run --table demo_customers --type Customer \
        --match-keys full_name,email [--key-column id] [--tag] [--relate]

The deterministic spine (discover -> resolve -> project) runs without an LLM;
--tag and --relate opt into the cheap/frontier tiers when models are configured.
"""
from __future__ import annotations

import argparse
import logging

from aryx.broker import default_broker
from aryx.config import get_settings
from aryx.connectors.postgres import PostgresConnector
from aryx.logging_setup import configure_logging
from aryx.pipeline.orchestrate import run_pipeline
from aryx.store.migrate import apply_migrations

logger = logging.getLogger(__name__)


def _run(args: argparse.Namespace) -> None:
    """Build a Postgres source connector and run the full pipeline."""
    settings = get_settings()
    apply_migrations(settings.rdb_dsn)
    connector = PostgresConnector(
        dsn=settings.rdb_dsn, table=args.table,
        key_column=args.key_column, batch_size=settings.batch_size,
    )
    summary = run_pipeline(
        connector=connector, dsn=settings.rdb_dsn, system=args.system,
        dataset=args.table, ontology_type=args.type,
        match_keys=[k.strip() for k in args.match_keys.split(",") if k.strip()],
        graph_url=settings.graph_url, broker=default_broker(),
        tag=args.tag, relate=args.relate,
    )
    logger.info("E2E summary %s", summary)


def main() -> None:
    """Parse arguments and dispatch the requested command."""
    parser = argparse.ArgumentParser(prog="aryx", description="Aryx pipeline CLI.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run a source end-to-end into the graph.")
    run.add_argument("--table", required=True, help="Source table to ingest.")
    run.add_argument("--type", required=True, help="Pinned ontology type.")
    run.add_argument("--match-keys", required=True,
                     help="Comma-separated payload keys for resolution match text.")
    run.add_argument("--key-column", default="id", help="Source primary key column.")
    run.add_argument("--system", default="postgresql", help="Source system label.")
    run.add_argument("--tag", action="store_true", help="Enable cheap-tier tagging.")
    run.add_argument("--relate", action="store_true",
                     help="Enable frontier relationship inference.")
    run.set_defaults(func=_run)
    args = parser.parse_args()
    configure_logging(get_settings().log_level)
    args.func(args)


if __name__ == "__main__":
    main()
