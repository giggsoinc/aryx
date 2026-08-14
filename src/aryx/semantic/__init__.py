"""Semantic Field Interpreter (C04).

Maps technical column names to grounded business concepts drawn from the
workspace ontology (types + attributes = the approved vocabulary), preserving
confidence, alternatives, and provenance. Deterministic-first: lexical + local
embedding similarity. A column that has no confident, grounded match is left
UNRESOLVED rather than guessed.
"""

from aryx.semantic.interpret import Term, interpret
from aryx.semantic.models import (
    SemanticAnnotation,
    SemanticProfile,
    UnresolvedField,
)

__all__ = [
    "interpret",
    "Term",
    "SemanticAnnotation",
    "SemanticProfile",
    "UnresolvedField",
]
