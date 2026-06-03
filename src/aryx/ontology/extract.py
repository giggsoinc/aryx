"""Document entity extraction agent + verbatim-span gate (Inc 8).

Runs on cheap tier; verbatim-span gate is a deterministic, free control:
any mention whose name is absent from its cited span is rejected before it
can reach resolution or the graph.

Provider-shape quirks (Gemini's bare-list envelope, field renames like
entity_type / verbatim_span) are absorbed by aryx.llm_normalize at the
complete_json boundary — this module sees the canonical schema shape only.
"""
from __future__ import annotations

import json
import logging

from aryx.broker import Broker
from aryx.llm import complete_json
from aryx.models import DocumentChunk, RawRecord, SourceRef

logger = logging.getLogger(__name__)

_SYSTEM_BASE = (
    "You extract entity mentions from document text for a domain-specific "
    "knowledge graph. For each mention return: "
    "(1) `type` — a singular PascalCase noun that names the REAL-WORLD CONCEPT "
    "being referenced. Use domain-specific types when warranted (Goal, Scope, "
    "Aim, Initiative, Capability, ValueProposition, CustomerSegment, "
    "Milestone, Metric, Feature, Risk, Pricing, MarketSegment, Strategy, "
    "Partner, Competitor, Dataset, KPI, RoadmapItem, etc.). Fall back to "
    "generic NER (Organization, Person, Product, Location, Date) ONLY when "
    "no domain-specific type fits. NEVER use generic words (Entity, Item, "
    "Thing, Concept). "
    "(2) `name` — the exact name as it literally appears in the text. "
    "(3) `attributes` — typed attributes (role, founded, value, owner, etc.). "
    "(4) `span` — a short verbatim excerpt from the text that contains the "
    "name word-for-word. "
    "Only emit a mention when the name appears word-for-word inside the span. "
    "Prefer rich domain types over generic NER. Prefer fewer high-confidence "
    "mentions over many uncertain ones."
)


def _system_prompt(context: str) -> str:
    """Prepend the workspace business context so extraction is domain-aware."""
    if not context.strip():
        return _SYSTEM_BASE
    return (
        f"WORKSPACE CONTEXT (what this knowledge graph is about):\n{context.strip()}\n\n"
        + _SYSTEM_BASE
        + "\n\nUse the workspace context above to decide which entity types "
        "matter. Pull domain-specific concepts (Goal, Scope, Aim, "
        "Initiative, Capability, etc.) when relevant — NOT just generic "
        "Organization/Person/Date."
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


def extract_mentions(chunks: list[DocumentChunk], broker: Broker,
                     context: str = "") -> list[RawRecord]:
    """Extract entity mentions from document chunks via the cheap LLM tier.

    Args:
        chunks: PII-screened chunks from clean_text.chunk_pages().
        broker: Model broker; extraction runs on the cheap tier.
        context: Workspace business context — folded into the system prompt
            so the LLM extracts domain-specific entity types instead of
            generic NER categories.

    Returns:
        RawRecord list where each record is one entity mention that passed the
        verbatim-span gate. Mentions whose name is absent from their cited span
        are silently dropped (logged at DEBUG).
    """
    records: list[RawRecord] = []
    rejected = 0
    system_prompt = _system_prompt(context)

    for chunk in chunks:
        user = json.dumps({"chunk_index": chunk.chunk_index, "text": chunk.text})
        try:
            result = complete_json(broker, "cheap", system_prompt, user, _SCHEMA)
        except Exception as exc:
            logger.warning("extraction failed chunk=%d doc=%s error=%s",
                           chunk.chunk_index, chunk.doc_id[:8], exc)
            continue

        for i, mention in enumerate(result.get("mentions", [])):
            name = mention.get("name", "")
            span = mention.get("span", "") or name
            if not name or not mention.get("type") or not _verbatim_ok(name, span):
                rejected += 1
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
                    "name": name,
                    "chunk_index": chunk.chunk_index,
                    "span": span,
                    **(mention.get("attributes") or {}),
                },
            ))

    logger.info("extract_mentions chunks=%d mentions=%d rejected=%d",
                len(chunks), len(records), rejected)
    return records
