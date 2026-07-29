"""Glue: interpret a profiled dataset against the ontology and persist (C04).

Shared by the ingest auto-trigger, backfill, and API. Loads the C03 profile and
the workspace ontology vocabulary, optionally embeds via the broker (local
model), runs the interpreter, and saves the semantic profile.
"""
from __future__ import annotations

import logging

from aryx.semantic.interpret import Term, column_text, interpret, make_terms
from aryx.semantic.models import SemanticProfile
from aryx.store.dataset_store import DatasetStore
from aryx.store.ontology_store import OntologyStore
from aryx.store.profile_store import ProfileStore
from aryx.store.semantic_store import SemanticStore

logger = logging.getLogger(__name__)


def _resolve_domain(dsn: str, workspace_id: int, dataset_id: str) -> str:
    """Best-effort: dataset -> C01 request_id -> intent domain (provenance only)."""
    try:
        dstore = DatasetStore(dsn, workspace_id)
        try:
            latest = dstore.latest(dataset_id)
        finally:
            dstore.close()
        if not latest or not latest.request_id:
            return ""
        from aryx.store.intent_store import IntentStore
        istore = IntentStore(dsn, workspace_id)
        try:
            intent = istore.get(latest.request_id)
        finally:
            istore.close()
        return intent.domain if intent else ""
    except Exception:  # noqa: BLE001 — domain is metadata, never block
        return ""


def _embeddings(broker, columns: list[str], terms: list[Term]) -> dict[str, list[float]] | None:
    """Embed column + term texts via the local model; None on any failure."""
    if broker is None or not terms:
        return None
    try:
        texts = sorted({column_text(c) for c in columns} | {t.text for t in terms})
        vecs = broker.embed(texts)
        if vecs and len(vecs) == len(texts):
            return dict(zip(texts, vecs))
    except Exception:  # noqa: BLE001 — fall back to lexical-only
        logger.debug("semantic embeddings unavailable; lexical only", exc_info=True)
    return None


def run_interpret(dsn: str, workspace_id: int, dataset_id: str,
                  version: str | None = None, *, domain: str = "",
                  broker=None) -> SemanticProfile | None:
    """Interpret a dataset version's columns and persist the semantic profile."""
    pstore = ProfileStore(dsn, workspace_id)
    try:
        profile = pstore.get(dataset_id, version) if version else pstore.latest(dataset_id)
    finally:
        pstore.close()
    if profile is None:
        return None

    ostore = OntologyStore(dsn, workspace_id)
    try:
        types = ostore.list_types()
    finally:
        ostore.close()
    terms = make_terms([(t.name, t.attributes) for t in types])

    resolved_domain = domain or _resolve_domain(dsn, workspace_id, dataset_id)
    vectors = _embeddings(broker, [c.name for c in profile.columns], terms)

    sp = interpret(profile, terms, domain=resolved_domain, vectors=vectors)
    sstore = SemanticStore(dsn, workspace_id)
    try:
        sstore.save(sp)
    finally:
        sstore.close()
    logger.info("interpreted dataset=%s version=%s annotations=%d unresolved=%d embed=%s",
                dataset_id, sp.dataset_version, len(sp.annotations),
                len(sp.unresolved_fields), vectors is not None)
    return sp
