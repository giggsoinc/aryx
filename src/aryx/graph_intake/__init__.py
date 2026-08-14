"""Knowledge Graph Intake & Validation (C05).

Accepts a knowledge-graph JSON (auto-derived from the workspace's Aryx entities
and relationships), validates it deterministically, normalizes it into the
internal canonical model without changing business meaning, computes a content
hash, and stores the original JSON immutably with a validated version. Exposes
bounded adapter reads for the downstream graph profiler. No LLM.
"""

from aryx.graph_intake.build import build_graph_json
from aryx.graph_intake.models import GraphIntakeResult, ValidationIssue
from aryx.graph_intake.validate import validate_and_normalize

__all__ = ["build_graph_json", "validate_and_normalize", "GraphIntakeResult", "ValidationIssue"]
