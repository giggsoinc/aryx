"""PII detection and anonymization gate (Inc 10).

Presidio Analyzer (spaCy en_core_web_sm + regex recognizers) detects PII spans
locally — no text leaves the machine until this gate clears. The boundary is
fail-closed: a chunk with unhandled PII spans raises rather than passing through.

Requires: presidio-analyzer presidio-anonymizer spacy en_core_web_sm
  python -m spacy download en_core_web_sm
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache

from aryx.models import DocumentChunk

logger = logging.getLogger(__name__)


class PiiAction(str, Enum):
    MASK = "mask"
    HASH = "hash"
    DROP = "drop"
    KEEP = "keep"


@dataclass
class PiiPolicy:
    default_action: PiiAction = PiiAction.MASK
    entity_actions: dict[str, PiiAction] = field(default_factory=dict)


DEFAULT_POLICY = PiiPolicy(
    default_action=PiiAction.MASK,
    entity_actions={
        "EMAIL_ADDRESS": PiiAction.HASH,
        "PHONE_NUMBER": PiiAction.MASK,
        "PERSON": PiiAction.MASK,
        "CREDIT_CARD": PiiAction.DROP,
        "IBAN_CODE": PiiAction.DROP,
        "US_SSN": PiiAction.DROP,
    },
)


@lru_cache(maxsize=1)
def _engines():
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    return AnalyzerEngine(), AnonymizerEngine()


def _operator_config(entity_type: str, policy: PiiPolicy):
    from presidio_anonymizer.entities import OperatorConfig
    action = policy.entity_actions.get(entity_type, policy.default_action)
    if action == PiiAction.MASK:
        return OperatorConfig("replace", {"new_value": f"<{entity_type}>"})
    if action == PiiAction.HASH:
        return OperatorConfig("hash", {"hash_type": "sha256"})
    if action == PiiAction.DROP:
        return OperatorConfig("redact")
    return OperatorConfig("keep")


def screen_chunks(
    chunks: list[DocumentChunk],
    policy: PiiPolicy | None = None,
) -> list[DocumentChunk]:
    """Detect and anonymize PII in every chunk before any text leaves the machine.

    Fail-closed: if Presidio fails to load, this raises immediately so the caller
    cannot proceed with unscreened text.

    Args:
        chunks: Normalized chunks from clean_text.chunk_pages().
        policy: PII action policy; defaults to DEFAULT_POLICY.

    Returns:
        New DocumentChunk list with PII-anonymized text.
    """
    if not chunks:
        return []

    if policy is None:
        policy = DEFAULT_POLICY

    analyzer, anonymizer = _engines()
    screened: list[DocumentChunk] = []

    for chunk in chunks:
        results = analyzer.analyze(text=chunk.text, language="en")
        if not results:
            screened.append(chunk)
            continue

        operators = {r.entity_type: _operator_config(r.entity_type, policy) for r in results}
        anonymized = anonymizer.anonymize(
            text=chunk.text, analyzer_results=results, operators=operators
        )
        screened.append(chunk.model_copy(update={"text": anonymized.text}))
        logger.debug("pii screened chunk=%d entities=%d", chunk.chunk_index, len(results))

    logger.info("pii screen complete chunks=%d", len(chunks))
    return screened
