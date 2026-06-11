"""Multi-key blocking for entity resolution.

Emits three key families per record so that transpositions (token-set key)
and phonetic near-misses (Soundex key) land in the same candidate block as
the naive prefix key.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict

from aryx.models import ResolutionRecord

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")

# Standard Soundex encoding table (A-Z, 26 chars each).
# 0 = A B H E I O U W Y   1 = B F P V   2 = C G J K Q S X Z
# 3 = D T   4 = L   5 = M N   6 = R
_SOUNDEX_FROM = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_SOUNDEX_TO   = "01230120022455012623010202"
_SOUNDEX_TABLE = str.maketrans(_SOUNDEX_FROM, _SOUNDEX_TO)


def normalize(value: str) -> str:
    """Lowercase, strip, and collapse internal whitespace for matching."""
    return _WS.sub(" ", value.lower().strip())


def soundex(word: str) -> str:
    """Return the 4-character Soundex code for *word*.

    Implements the standard American Soundex algorithm inline so no external
    dependency is required.
    """
    if not word:
        return "0000"
    word = word.upper()
    code = word[0]
    digits = word[1:].translate(_SOUNDEX_TABLE)
    # Remove consecutive duplicates and zeros; treat the retained first-char
    # digit as the previous code so we don't double-encode it.
    prev = code.translate(_SOUNDEX_TABLE)
    result = ""
    for d in digits:
        if d != "0" and d != prev:
            result += d
        prev = d
    return (code + result + "000")[:4]


def _keys_for(text: str) -> list[str]:
    """Return all three blocking keys for *text*."""
    normed = normalize(text)
    tokens = normed.split()

    prefix_key = "prefix:" + normed[:4]
    token_key = "tokens:" + "|".join(sorted(set(tokens)))[:32]
    first_token = tokens[0] if tokens else ""
    soundex_key = "soundex:" + soundex(first_token)

    return [prefix_key, token_key, soundex_key]


class MultiKeyBlocker:
    """Group records into candidate blocks using three key families.

    Each record is placed in every block whose key it produces, so pairs that
    share *any* key become candidates.  Blocks larger than *max_block_size*
    are skipped with a WARNING to prevent O(n^2) blowup on degenerate data.

    Args:
        max_block_size: Blocks with more members than this are dropped.
    """

    def __init__(self, max_block_size: int = 5000) -> None:
        self.max_block_size = max_block_size

    def block(
        self, records: list[ResolutionRecord]
    ) -> dict[str, list[ResolutionRecord]]:
        """Assign records to blocks and return key -> record-list mapping.

        Args:
            records: Records to block.

        Returns:
            Mapping of blocking key to the list of records in that block.
            Oversized blocks are omitted entirely.
        """
        raw: dict[str, list[ResolutionRecord]] = defaultdict(list)
        for record in records:
            for key in _keys_for(record.text):
                raw[key].append(record)

        result: dict[str, list[ResolutionRecord]] = {}
        for key, members in raw.items():
            if len(members) > self.max_block_size:
                logger.warning(
                    "Block '%s' has %d members (> max_block_size=%d) -- skipping.",
                    key,
                    len(members),
                    self.max_block_size,
                )
                continue
            result[key] = members
        return result
