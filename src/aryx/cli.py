"""CLI for the end-to-end pipeline (Increment 7) and document ingestion (Increment 8).

Usage:
    aryx run --table demo_customers --type Customer --match-keys full_name,email
    aryx docs --paths report.pdf deck.pptx --type Contract --match-keys name

The deterministic spine (discover -> resolve -> project) runs without an LLM;
--tag, --relate, and --no-pii opt into or out of LLM/PII stages.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

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


def _docs(args: argparse.Namespace) -> None:
    """Ingest documents through the doc pipeline and into the graph."""
    from aryx.connectors.doc_router import DocumentRouterConnector
    from aryx.store.chunk_store import ChunkStore

    settings = get_settings()
    apply_migrations(settings.rdb_dsn)
    broker = default_broker()

    chunk_store = ChunkStore(settings.rdb_dsn)
    chunk_store.check_embed_compat(
        model_id=broker.embed_model_id or "",
        dim=settings.embed_dim,
    )

    paths = [Path(p) for p in args.paths]
    connector = DocumentRouterConnector(
        paths=paths,
        system=args.system,
        broker=broker,
        chunk_store=chunk_store,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        expected_embed_dim=settings.embed_dim,
        run_pii=not args.no_pii,
    )
    summary = run_pipeline(
        connector=connector, dsn=settings.rdb_dsn, system=args.system,
        dataset="documents", ontology_type=args.type,
        match_keys=[k.strip() for k in args.match_keys.split(",") if k.strip()],
        graph_url=settings.graph_url, broker=broker,
        tag=args.tag, relate=args.relate,
    )
    chunk_store.close()
    logger.info("docs E2E summary %s", summary)


def main() -> None:
    """Parse arguments and dispatch the requested command."""
    parser = argparse.ArgumentParser(prog="aryx", description="Aryx pipeline CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a DB table end-to-end into the graph.")
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

    docs = sub.add_parser("docs", help="Ingest documents (PDF/PPTX/DOCX/image/JSON).")
    docs.add_argument("--paths", nargs="+", required=True, help="Document file paths.")
    docs.add_argument("--type", required=True, help="Pinned ontology type for extracted entities.")
    docs.add_argument("--match-keys", required=True,
                      help="Comma-separated payload keys for resolution match text.")
    docs.add_argument("--system", default="documents", help="Source system label.")
    docs.add_argument("--no-pii", action="store_true", help="Skip the Presidio PII gate.")
    docs.add_argument("--tag", action="store_true", help="Enable cheap-tier tagging.")
    docs.add_argument("--relate", action="store_true",
                      help="Enable frontier relationship inference.")
    docs.set_defaults(func=_docs)

    args = parser.parse_args()
    configure_logging(get_settings().log_level)
    args.func(args)


if __name__ == "__main__":
    main()
