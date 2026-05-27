"""Container entry point: configure logging and report readiness.

The full pipeline runner arrives in later increments; for now this verifies
the package imports cleanly and the worker container is healthy.
"""
from __future__ import annotations

import logging

from aryx import __version__
from aryx.config import get_settings
from aryx.logging_setup import configure_logging
from aryx.store.migrate import apply_migrations

logger = logging.getLogger(__name__)


def main() -> None:
    """Configure logging, apply the landing schema, and report readiness."""
    settings = get_settings()
    configure_logging(settings.log_level)
    apply_migrations(settings.rdb_dsn)
    # Log only the host/db portion of the DSN — never the credentials.
    target = settings.rdb_dsn.split("@")[-1]
    logger.info("aryx %s ready rdb=%s", __version__, target)


if __name__ == "__main__":
    main()
