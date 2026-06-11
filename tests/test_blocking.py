"""Tests for multi-key blocking (G2 gap closure)."""
from __future__ import annotations

import logging
import unittest

from aryx.models import ResolutionRecord
from aryx.resolution.blocking import MultiKeyBlocker, soundex
from aryx.resolution.classical import block, block_key, normalize


def _rec(record_id: int, text: str) -> ResolutionRecord:
    return ResolutionRecord(record_id=record_id, text=text, payload={})


class TestSoundex(unittest.TestCase):
    def test_smith_smyth_equivalent(self) -> None:
        """soundex("Smith") == soundex("Smyth") — phonetic equivalence."""
        assert soundex("Smith") == soundex("Smyth"), (
            f"Expected equal codes, got {soundex('Smith')!r} vs {soundex('Smyth')!r}"
        )

    def test_schmidt_schmit_equivalent(self) -> None:
        """soundex("Schmidt") == soundex("Schmit") — near-miss phonetic."""
        assert soundex("Schmidt") == soundex("Schmit"), (
            f"Expected equal codes, got {soundex('Schmidt')!r} vs {soundex('Schmit')!r}"
        )

    def test_empty_word(self) -> None:
        assert soundex("") == "0000"

    def test_single_char(self) -> None:
        code = soundex("A")
        assert len(code) == 4
        assert code[0] == "A"


class TestMultiKeyBlocker(unittest.TestCase):
    def _shared_keys(self, text_a: str, text_b: str) -> set[str]:
        blocker = MultiKeyBlocker()
        records = [_rec(1, text_a), _rec(2, text_b)]
        blocks = blocker.block(records)
        keys_a = {k for k, members in blocks.items() if any(r.record_id == 1 for r in members)}
        keys_b = {k for k, members in blocks.items() if any(r.record_id == 2 for r in members)}
        return keys_a & keys_b

    def test_transposition_shares_token_set_key(self) -> None:
        """John Smith and Smith John share a token-set block key."""
        shared = self._shared_keys("John Smith", "Smith John")
        token_keys = {k for k in shared if k.startswith("tokens:")}
        assert token_keys, (
            "Expected at least one shared tokens: key for transposition pair"
        )

    def test_phonetic_near_miss_shares_soundex_key(self) -> None:
        """Schmidt and Schmit share a Soundex block key."""
        shared = self._shared_keys("Schmidt", "Schmit")
        soundex_keys = {k for k in shared if k.startswith("soundex:")}
        assert soundex_keys, (
            "Expected at least one shared soundex: key for phonetic near-miss"
        )

    def test_no_false_positive_smith_jones(self) -> None:
        """Smith and Jones do NOT share any block key."""
        shared = self._shared_keys("Smith", "Jones")
        assert not shared, f"Unexpected shared keys for Smith/Jones: {shared}"

    def test_oversized_block_skipped_and_logged(self) -> None:
        """A block with >5000 records is skipped entirely and a WARNING is logged."""
        cap = 5
        blocker = MultiKeyBlocker(max_block_size=cap)
        # All records share the same prefix/token/soundex keys
        records = [_rec(i, "aaaa test") for i in range(cap + 1)]
        with self.assertLogs(level=logging.WARNING) as cm:
            result = blocker.block(records)
        # Every key should be oversized and therefore skipped
        assert result == {}, f"Expected empty result, got keys: {list(result.keys())}"
        assert any("skipping" in msg.lower() for msg in cm.output), (
            "Expected a WARNING log mentioning skipping"
        )

    def test_record_appears_in_multiple_blocks(self) -> None:
        """A single record generates up to three distinct keys."""
        blocker = MultiKeyBlocker()
        records = [_rec(1, "John Smith")]
        blocks = blocker.block(records)
        keys = {k for k, members in blocks.items() if any(r.record_id == 1 for r in members)}
        # Should have prefix:, tokens:, and soundex: keys
        assert any(k.startswith("prefix:") for k in keys)
        assert any(k.startswith("tokens:") for k in keys)
        assert any(k.startswith("soundex:") for k in keys)


class TestClassicalRegressions(unittest.TestCase):
    """normalize and block_key from classical.py must remain unchanged."""

    def test_normalize_lowercases_and_strips(self) -> None:
        assert normalize("  Hello   World  ") == "hello world"

    def test_normalize_collapses_whitespace(self) -> None:
        assert normalize("foo   bar") == "foo bar"

    def test_block_key_is_first_four_chars_normalized(self) -> None:
        assert block_key("Hello World") == "hell"
        assert block_key("  AB  ") == "ab"

    def test_shim_block_returns_dict(self) -> None:
        """classical.block() shim delegates to MultiKeyBlocker."""
        records = [_rec(1, "Alice"), _rec(2, "Alice Bob")]
        result = block(records)
        assert isinstance(result, dict)
        assert len(result) >= 1


if __name__ == "__main__":
    unittest.main()
