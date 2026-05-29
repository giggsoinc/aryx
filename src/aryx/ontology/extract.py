"""Document entity extraction agent + verbatim-span gate (Inc 8).

Runs on cheap tier; verbatim-span gate is a deterministic, free control:
any mention whose name is absent from its cited span is rejected before it
can reach resolution or the graph.
"""
from __future__ import annotations

import json
import logging

from aryx.broker import Broker
from aryx.llm import complete_json
from aryx.models import DocumentChunk, RawRecord, SourceRef

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You extract named entity mentions from document text. "
    "For each mention return the entity type (Organization, Person, Location, Product, "
    "Date, or other relevant type), the exact name as it literally appears in the text, "
    "any typed attributes (e.g. founded, role, country), and a verbatim span — a short "
    "excerpt from the text that contains the name. "
    "Only emit a mention when the name appears word-for-word inside the span. "
    "Be conservative: prefer fewer high-confidence mentions over many uncertain ones."
)

_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "name": {"type": "string"},
                    "attributes": {"type": "object", "additionalProperties": True},
                    "span": {"type": "string"},
                },
                "required": ["type", "name", "span"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["mentions"],
    "additionalProperties": False,
}


def _verbatim_ok(name: str, span: str) -> bool:
    return name.lower() in span.lower()


def extract_mentions(chunks: list[DocumentChunk], broker: Broker) -> list[RawRecord]:
    """Extract entity mentions from document chunks via the cheap LLM tier.

    Args:
        chunks: PII-screened chunks from clean_text.chunk_pages().
        broker: Model broker; extraction runs on the cheap tier.

    Returns:
        RawRecord list where each record is one entity mention that passed the
        verbatim-span gate. Mentions whose name is absent from their cited span
        are silently dropped (logged at DEBUG).
    """
    records: list[RawRecord] = []
    rejected = 0

    for chunk in chunks:
        user = json.dumps({"chunk_index": chunk.chunk_index, "text": chunk.text})
        try:
            result = complete_json(broker, "cheap", _SYSTEM, user, _SCHEMA)
        except Exception as exc:
            logger.warning("extraction failed chunk=%d doc=%s error=%s",
                           chunk.chunk_index, chunk.doc_id[:8], exc)
            continue

        for i, mention in enumerate(result.get("mentions", [])):
            if not _verbatim_ok(mention["name"], mention["span"]):
                rejected += 1
                logger.debug("verbatim-span gate rejected name=%r chunk=%d",
                             mention["name"], chunk.chunk_index)
                continue
            mention_id = f"{chunk.doc_id}:{chunk.chunk_index}:{i}"
            records.append(RawRecord(
                source=SourceRef(
                    system=chunk.source.system,
                    dataset=chunk.source.dataset,
                    record_id=mention_id,
                ),
                payload={
                    "type": mention["type"],
                    "name": mention["name"],
                    "chunk_index": chunk.chunk_index,
                    "span": mention["span"],
                    **mention.get("attributes", {}),
                },
            ))

    logger.info("extract_mentions chunks=%d mentions=%d rejected=%d",
                len(chunks), len(records), rejected)
    return records
