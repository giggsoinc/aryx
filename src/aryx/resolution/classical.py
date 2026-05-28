"""Classical ER helpers: normalize, block, and score (cheap, deterministic)."""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from aryx.models import ResolutionRecord

_WS = re.compile(r"\s+")


def normalize(value: str) -> str:
    """Lowercase, strip, and collapse internal whitespace for matching."""
    return _WS.sub(" ", value.lower().strip())


def block_key(text: str) -> str:
    """Cheap blocking key: first 4 chars of the normalized text.

    Records sharing a key are candidates; this bounds pairwise work to within
    small blocks instead of comparing every record to every other (n^2).
    """
    return normalize(text)[:4]


def block(records: list[ResolutionRecord]) -> dict[str, list[ResolutionRecord]]:
    """Group records into candidate blocks by block key."""
    blocks: dict[str, list[ResolutionRecord]] = {}
    for record in records:
        blocks.setdefault(block_key(record.text), []).append(record)
    return blocks


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
