"""Aryx capability ports — the hexagonal seam (v2 Phase 0).

Every v2 feature talks to a *capability port* (an interface), never a concrete
store. The active adapter set is resolved from config by the container, so
swapping the substrate — Postgres -> Oracle ADB, FalkorDB -> Oracle RDF,
Ollama -> OCI GenAI — is an adapter swap, not a rewrite. This is what makes
Aryx-o (v2.1) cheap and keeps the Engine (the IP) substrate-agnostic.

Use ``ports()`` to reach the active container::

    from aryx.ports import ports
    reader = ports().graph_reader(workspace_id)

See docs/EDITIONS.md and temp_design/ontology-v2/08-v2-attack-plan.html.
"""
from __future__ import annotations

from aryx.ports.container import Container, ports
from aryx.ports.protocols import (
    ComputePort,
    GraphReaderPort,
    GraphStorePort,
    LlmPort,
    ReasonerPort,
    RelationalPort,
    VectorPort,
)

__all__ = [
    "Container",
    "ports",
    "GraphReaderPort",
    "GraphStorePort",
    "RelationalPort",
    "VectorPort",
    "LlmPort",
    "ReasonerPort",
    "ComputePort",
]
