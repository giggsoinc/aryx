"""Application configuration loaded from the environment (12-factor)."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

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
    log_level: str = Field(default="INFO", description="Root log level.")
    batch_size: int = Field(default=500, description="Rows fetched per extract batch.")
    embed_dim: int = Field(default=768, description="Expected embedding dim; startup check fails on mismatch.")
    chunk_size: int = Field(default=1000, description="Target chunk size in characters.")
    chunk_overlap: int = Field(default=100, description="Overlap in characters between adjacent chunks.")
    max_block_size: int = Field(default=5000, description="Resolution blocking: blocks with more members than this are skipped.")
    ask_attributes: Literal["off", "safe", "all"] = Field(
        default="safe",
        description="What record field values Ask puts in the answer model's "
                    "prompt (the model may be a hosted provider). 'off' sends "
                    "none (counts and names only); 'safe' sends them but drops "
                    "attributes whose name or value looks personal or secret "
                    "(email, phone, address, card/account numbers, tokens, ...); "
                    "'all' sends everything.",
    )
    ask_overview_ttl: int = Field(
        default=300, ge=0,
        description="Seconds Ask caches a workspace overview (exact type counts, "
                    "value breakdowns, sample names) in each API process. It is "
                    "dropped immediately when the graph changes in that process "
                    "(other API processes pick the change up when their entry "
                    "expires). 0 disables the cache.",
    )
    ask_breakdown_max_entities: int = Field(
        default=50000, ge=0,
        description="Largest workspace (in entities) for which Ask computes "
                    "value counts such as 'status: open 26'. That pass reads "
                    "every attribute of every entity (about 4-6 s per 100k "
                    "entities), so above this size the overview keeps the exact "
                    "type counts and sample names but omits the value counts. "
                    "0 = no limit.",
    )
    blob_dir: str = Field(
        default="/data/aryx-blobs",
        description="On-disk root for raw dataset upload bytes (aryx.store."
                    "blob_store), content-addressed by SHA-256. Postgres "
                    "keeps hash + metadata only — never the bytes.",
    )
    auto_chain_enabled: bool = Field(
        default=False,
        description="Gate for the zero-click Brief->Dashboard auto-chain "
                    "(aryx.pipeline.chain_jobs). Off by default: the chain "
                    "calls a real LLM (planner) and runs analysis execution "
                    "on every valid intent/brief/ingest, so an unauthenticated "
                    "or optionally-authenticated caller could otherwise "
                    "trigger real spend just by hitting the API. Manual "
                    "per-stage buttons always work regardless of this flag.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
