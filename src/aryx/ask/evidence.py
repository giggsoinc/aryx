"""The retrieved-evidence model — driver-free so the verifier stays pure.

Lives outside the graph package so the groundedness engine can import it
without pulling in the FalkorDB driver. ``graph.retrieve`` produces these;
``ask.grounding`` verifies against them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedEntity:
    """One entity that fed an answer, with its one-hop context + provenance."""

    id: int
    type: str
    name: str
    neighbors: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
