"""Pure naming helpers — no driver imports, safe for the composition root.

Kept dependency-free so ``aryx.ports`` (the hexagonal seam) can name a
workspace graph without importing psycopg / FalkorDB. ``aryx.workspaces``
re-exports ``ws_graph`` for backward compatibility.
"""
from __future__ import annotations


def ws_graph(workspace_id: int) -> str:
    """FalkorDB graph name for a workspace."""
    return f"aryx_ws_{int(workspace_id)}"
