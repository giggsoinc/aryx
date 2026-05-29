"""Chunk embedding via the broker's local Ollama embed model (Inc 9).

Fail-closed: raises RuntimeError if the broker has no embed model configured
or if the returned dimension doesn't match the expected dim. This prevents
mixed-dim vectors from entering the store silently.
"""
from __future__ import annotations

import logging

from aryx.broker import Broker
from aryx.models import ChunkEmbedding, DocumentChunk

logger = logging.getLogger(__name__)


def embed_chunks(
    chunks: list[DocumentChunk],
    broker: Broker,
    expected_dim: int | None = None,
) -> list[ChunkEmbedding]:
    """Embed a batch of chunks via broker.embed() (local Ollama model).

    Args:
        chunks: DocumentChunk list to embed.
        broker: Model broker; embed() is called on the local Ollama endpoint.
        expected_dim: When set, raises RuntimeError on dim mismatch (startup guard).

    Returns:
        One ChunkEmbedding per input chunk, in the same order.
    """
    if not chunks:
        return []

    model_id = broker.embed_model_id
    if not model_id:
        raise RuntimeError(
            "no embed model configured — set broker catalog embed.model"
        )

    texts = [c.text for c in chunks]
    vectors = broker.embed(texts)
    if not vectors:
        raise RuntimeError(
            f"broker.embed() returned no vectors for model={model_id!r} — "
            "is Ollama running and the model pulled?"
        )

    dim = len(vectors[0])
    if expected_dim is not None and dim != expected_dim:
        raise RuntimeError(
            f"embed dim mismatch: model={model_id!r} produced {dim}, "
            f"expected {expected_dim}. Update config or re-embed."
        )

    logger.info("embedded chunks=%d model=%s dim=%d", len(chunks), model_id, dim)
    return [
        ChunkEmbedding(
            chunk_index=chunk.chunk_index,
            doc_id=chunk.doc_id,
            model_id=model_id,
            dim=dim,
            vector=vec,
        )
        for chunk, vec in zip(chunks, vectors)
    ]
