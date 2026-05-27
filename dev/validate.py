"""DEV ONLY — end-to-end validation runner (run on the EC2, not in prod).

Applies the schema, then drives discover() over the synthetic demo_customers
table seeded by dev/seed.sql. Verify the result by querying aryx_field_profile
(the 'email' field should show non_null=3, proving clean() dropped the two
blank/whitespace emails). Not copied into the worker image.
"""
from __future__ import annotations

import logging

from aryx.config import get_settings
from aryx.connectors.postgres import PostgresConnector
from aryx.discover import discover
from aryx.logging_setup import configure_logging
from aryx.store.migrate import apply_migrations
from aryx.store.postgres_store import PostgresStore

logger = logging.getLogger(__name__)


def main() -> None:
    """Run discovery over the demo source under a tracked run."""
    settings = get_settings()
    configure_logging(settings.log_level)
    apply_migrations(settings.rdb_dsn)

    connector = PostgresConnector(
        dsn=settings.rdb_dsn,
        table="demo_customers",
        key_column="id",
        batch_size=settings.batch_size,
    )
    store = PostgresStore(settings.rdb_dsn)
    try:
        run_id = discover(
            connector, store, system="postgresql", dataset="demo_customers"
        )
        logger.info("validation complete run_id=%s — query aryx_field_profile", run_id)
    finally:
        store.close()


if __name__ == "__main__":
    main()
