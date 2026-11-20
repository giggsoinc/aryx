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
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from aryx.broker import Broker
from aryx.envnum import env_number
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


# Gemini answers one chunk in ~7 s; reading several at once keeps a long document
# in minutes. Both are overridable (a rate-limited key may want fewer workers).
_WORKERS = int(env_number("ARYX_EXTRACT_WORKERS", 3, int, minimum=1))
_ATTEMPTS = int(env_number("ARYX_EXTRACT_ATTEMPTS", 2, int, minimum=1))

Progress = Callable[[int, int, int], None]   # (chunks done, chunks total, mentions so far)


def _ask(chunk: DocumentChunk, broker: Broker, system_prompt: str,
         errors: list[str] | None = None) -> dict | None:
    """One chunk through the model; a failed or timed-out call is tried again.

    A single Gemini timeout used to lose the whole chunk. None means every
    attempt failed (the caller logs it and carries on with the other chunks).
    """
    user = json.dumps({"chunk_index": chunk.chunk_index, "text": chunk.text})
    for attempt in range(1, max(1, _ATTEMPTS) + 1):
        try:
            return complete_json(broker, "cheap", system_prompt, user, _SCHEMA)
        except Exception as exc:  # noqa: BLE001 - one chunk must not stop the document
            logger.warning("extraction failed chunk=%d doc=%s attempt=%d/%d error=%s",
                           chunk.chunk_index, chunk.doc_id[:8], attempt, _ATTEMPTS, exc)
            if errors is not None:
                errors.append(f"{type(exc).__name__}: {str(exc)[:120]}")
            if attempt < _ATTEMPTS:
                time.sleep(1.0)
    return None


def _records_of(chunk: DocumentChunk, result: dict) -> tuple[list[RawRecord], int]:
    """Mentions of one chunk that pass the verbatim-span gate, and the rejected count."""
    records: list[RawRecord] = []
    rejected = 0
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
    return records, rejected


def extract_mentions(chunks: list[DocumentChunk], broker: Broker,
                     context: str = "",
                     on_progress: Progress | None = None,
                     stats: dict | None = None) -> list[RawRecord]:
    """Extract entity mentions from document chunks via the cheap LLM tier.

    Args:
        chunks: PII-screened chunks from clean_text.chunk_pages().
        broker: Model broker; extraction runs on the cheap tier.
        context: Workspace business context - folded into the system prompt
            so the LLM extracts domain-specific entity types instead of
            generic NER categories.
        on_progress: Called as ``(chunks_done, chunks_total, mentions_so_far)``
            from the calling thread each time a chunk finishes.
        stats: Filled with ``failed`` (chunks every attempt failed on) and
            ``last_error``, so the caller can say why nothing came out.

    Returns:
        RawRecord list where each record is one entity mention that passed the
        verbatim-span gate, in chunk order whatever order the model answered in.
        Mentions whose name is absent from their cited span are dropped.
    """
    system_prompt = _system_prompt(context)
    results: dict[int, dict | None] = {}
    errors: list[str] = []
    found = 0
    with ThreadPoolExecutor(max_workers=max(1, _WORKERS)) as pool:
        futures = {pool.submit(_ask, c, broker, system_prompt, errors): n
                   for n, c in enumerate(chunks)}
        for done, fut in enumerate(as_completed(futures), start=1):
            n = futures[fut]
            results[n] = fut.result()
            if results[n]:
                found += len(results[n].get("mentions", []))
            if on_progress is not None:
                on_progress(done, len(chunks), found)

    records: list[RawRecord] = []
    rejected = failed = 0
    for n, chunk in enumerate(chunks):
        result = results.get(n)
        if result is None:
            failed += 1
            continue
        got, rej = _records_of(chunk, result)
        records.extend(got)
        rejected += rej

    if stats is not None:
        stats["failed"] = failed
        stats["last_error"] = errors[-1] if errors else ""
    logger.info("extract_mentions chunks=%d mentions=%d rejected=%d failed_chunks=%d",
                len(chunks), len(records), rejected, failed)
    return records
