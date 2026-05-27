"""Source connectors (pipeline stage 1: extract)."""

from aryx.connectors.base import Connector
from aryx.connectors.postgres import PostgresConnector

__all__ = ["Connector", "PostgresConnector"]
