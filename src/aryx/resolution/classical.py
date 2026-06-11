"""Classical ER helpers: normalize, block, and score (cheap, deterministic)."""
from __future__ import annotations

import math
from difflib import SequenceMatcher

from aryx.models import ResolutionRecord
from aryx.resolution.blocking import MultiKeyBlocker, normalize  # noqa: F401  (re-export)

# normalize is imported from blocking and re-exported for backward compatibility.
__all__ = ["normalize", "block_key", "block", "string_score", "cosine", "score_pair"]


def block_key(text: str) -> str:
    """Cheap blocking key: first 4 chars of the normalized text.

    Records sharing a key are candidates; this bounds pairwise work to within
    small blocks instead of comparing every record to every other (n^2).
    """
    return normalize(text)[:4]


def block(records: list[ResolutionRecord], max_block_size: int = 5000) -> dict[str, list[ResolutionRecord]]:
    """Group records into candidate blocks (shim for MultiKeyBlocker).

    Delegates to MultiKeyBlocker so all three key families (prefix, token-set,
    Soundex) are used.  Existing callers that import this function are
    unaffected.
    """
    return MultiKeyBlocker(max_block_size).block(records)


def string_score(left: str, right: str) -> float:
    """Similarity ratio of two strings in [0, 1]."""
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def cosine(left: list[float], right: list[float]) -> float:
    """Cosine similarity of two vectors in [0, 1] (0 if either is empty)."""
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def score_pair(
    left_text: str,
    right_text: str,
    left_emb: list[float] | None = None,
    right_emb: list[float] | None = None,
) -> float:
    """Blend string similarity with embedding cosine when embeddings exist."""
    text = string_score(left_text, right_text)
    if left_emb and right_emb:
        return 0.5 * text + 0.5 * cosine(left_emb, right_emb)
    return text
