"""Application configuration loaded from the environment (12-factor)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Aryx runtime settings sourced from ARYX_-prefixed env variables."""

    model_config = SettingsConfigDict(env_prefix="ARYX_", env_file=".env")

    rdb_dsn: str = Field(
        default="postgresql://aryx:aryx@localhost:5432/aryx",
        description="DSN for the canonical relational store (source of truth).",
    )
    graph_url: str = Field(
        default="redis://localhost:6379",
        description="Connection URL for the rebuildable FalkorDB projection.",
    )
    log_level: str = Field(default="INFO", description="Root log level.")
    batch_size: int = Field(default=500, description="Rows fetched per extract batch.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
