"""Application configuration loaded from the environment (12-factor)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Aryx runtime settings sourced from ARYX_-prefixed env variables."""

    # extra="ignore": a local .env commonly carries keys for other tools/
    # experiments (or legacy ARYX_ vars this schema no longer declares) —
    # those must not hard-crash every Settings() construction.
    model_config = SettingsConfigDict(env_prefix="ARYX_", env_file=".env", extra="ignore")

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
    embed_dim: int = Field(default=768, description="Expected embedding dim; startup check fails on mismatch.")
    chunk_size: int = Field(default=1000, description="Target chunk size in characters.")
    chunk_overlap: int = Field(default=100, description="Overlap in characters between adjacent chunks.")
    max_block_size: int = Field(default=5000, description="Resolution blocking: blocks with more members than this are skipped.")
    blob_dir: str = Field(
        default="/data/aryx-blobs",
        description="On-disk root for raw dataset upload bytes (aryx.store."
                    "blob_store), content-addressed by SHA-256. Postgres "
                    "keeps hash + metadata only — never the bytes.",
    )



@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
