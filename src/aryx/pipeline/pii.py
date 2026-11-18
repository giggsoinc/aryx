"""PII detection and anonymization gate (Inc 10).

Presidio Analyzer (spaCy en_core_web_sm + regex recognizers) detects PII spans
locally — no text leaves the machine until this gate clears. The boundary is
fail-closed: a chunk with unhandled PII spans raises rather than passing through.

Requires: presidio-analyzer presidio-anonymizer spacy en_core_web_sm
  python -m spacy download en_core_web_sm
"""
from __future__ import annotations

import logging
import os
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


_DEFAULT_SPACY_MODEL = "en_core_web_sm"


@lru_cache(maxsize=1)
def _engines():
    """Build the Presidio engines once, pinned to an explicit spaCy model.

    A bare ``AnalyzerEngine()`` silently picks ``en_core_web_lg`` (~400 MB) and,
    when that is not installed, DOWNLOADS it from GitHub at first use — inside
    the first document's ingest. In Docker that model is never baked in, so
    the first upload (pptx/pdf/docx alike) stalled on the download, hit the
    per-document timeout, or failed outright with no network. The Dockerfile
    now installs ``en_core_web_sm`` (documented above) at build time; override
    with ARYX_PII_SPACY_MODEL if a larger model is baked in.
    """
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine

    model = os.environ.get("ARYX_PII_SPACY_MODEL", _DEFAULT_SPACY_MODEL)
    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": model}],
    }).create_engine()
    logger.info("pii engine ready spacy_model=%s", model)
    return (AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"]),
            AnonymizerEngine())


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
