"""G10 follow-up: adjudicate() must read the schema field the LLM actually
returns AFTER shared normalization, not before.

Regression test for a real bug found this session: the schema asks the model
for `score`, but the shared llm_normalize.py synonym table renames `score` to
canonical `confidence` for every provider, including Anthropic's strict
structured output. Reading `result.get("score", ...)` after that rename
always misses and silently returns 0.0. This test exercises the real
complete_json() + _normalize_json() path (only the provider HTTP call is
mocked) so a regression to reading "score" fails loudly instead of just
degrading live adjudication quality.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from aryx.broker.specs import ModelSpec
from aryx.models import ResolutionRecord
from aryx.resolution.adjudicate import adjudicate


def _pair() -> tuple[ResolutionRecord, ResolutionRecord]:
    left = ResolutionRecord(record_id=1, text="Acme Robotics LLC",
                            payload={"name": "Acme Robotics LLC"})
    right = ResolutionRecord(record_id=2, text="Acme Robtcs LLC",
                             payload={"name": "Acme Robtcs LLC"})
    return left, right


def _fake_broker(spec: ModelSpec) -> MagicMock:
    broker = MagicMock()
    broker.choose.return_value = spec
    broker.secrets.get.return_value = None
    return broker


def test_adjudicate_reads_normalized_confidence_key() -> None:
    """Provider returns the schema's own 'score' key; normalize renames it to
    'confidence'; adjudicate() must read THAT, not 'score'."""
    left, right = _pair()
    spec = ModelSpec(name="claude-test", provider="anthropic", tier="frontier")
    broker = _fake_broker(spec)
    with patch("aryx.llm.anthropic_json",
               return_value=({"score": 0.85, "reason": "abbreviation match"}, 10, 5)):
        result = adjudicate(left, right, broker)
    assert result == 0.85


def test_adjudicate_defaults_to_zero_when_key_truly_missing() -> None:
    """No score/confidence at all -> 0.0, not a crash."""
    left, right = _pair()
    spec = ModelSpec(name="claude-test", provider="anthropic", tier="frontier")
    broker = _fake_broker(spec)
    with patch("aryx.llm.anthropic_json",
               return_value=({"reason": "no score field"}, 10, 5)):
        result = adjudicate(left, right, broker)
    assert result == 0.0
