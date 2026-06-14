"""Aryx Ask engine — retrieval-grounded answering + groundedness verification.

The Accuracy Lab (v2 Phase 1) is built on this package: every answer carries a
structured grounding record (which entities / sources it stands on) so the Lab
can show provenance and score ontology-on vs ontology-off fairly.
"""
from __future__ import annotations

from aryx.ask.grounding import Citation, Grounding, build_grounding

__all__ = ["Citation", "Grounding", "build_grounding"]
