"""Knowledge Graph Profiler (C06).

Summarizes the validated graph (from C05) into deterministic statistics and a
compact schema, and exposes only VERIFIED, bounded paths — every path is backed
by real relationship instances in the graph. A model may explain a verified
path, but it cannot invent a node, relationship, or path. No path exceeds the
requested depth bound.
"""

from aryx.graph_profiler.models import GraphProfile, VerifiedPath
from aryx.graph_profiler.profile import profile_graph

__all__ = ["profile_graph", "GraphProfile", "VerifiedPath"]
