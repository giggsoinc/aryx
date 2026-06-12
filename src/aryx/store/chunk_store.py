"""Postgres store for the vector plane: documents, chunks, and embeddings (Inc 9)."""
from __future__ import annotations

import logging

from aryx.models import ChunkEmbedding, DocumentChunk
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class ChunkStore:
    """Persists document metadata, text chunks, and dense embeddings."""

    def __init__(self, dsn: str) -> None:
        """Acquire the shared connection pool for this DSN."""
        self._pool = get_pool(dsn)

    def upsert_document(
        self, content_hash: str, file_name: str, source_type: str, byte_count: int
    ) -> int:
        """Upsert a document record and return its id."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("upsert_document"),
                            (content_hash, file_name, source_type, byte_count))
                row = cur.fetchone()
        doc_db_id = int(row[0]) if row else 0
        logger.info("upserted document hash=%s id=%d", content_hash[:8], doc_db_id)
        return doc_db_id

    def save_chunks(self, doc_db_id: int, chunks: list[DocumentChunk]) -> list[int]:
        """Persist text chunks and return their ids."""
        ids: list[int] = []
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                for chunk in chunks:
                    cur.execute(
                        load("insert_chunk"),
                        (doc_db_id, chunk.chunk_index, chunk.page_slide,
                         chunk.char_start, chunk.char_end, chunk.text),
                    )
                    row = cur.fetchone()
                    if row:
                        ids.append(int(row[0]))
        logger.info("saved chunks doc_id=%d count=%d", doc_db_id, len(ids))
        return ids

    def save_embeddings(self, chunk_db_ids: list[int],
                        embeddings: list[ChunkEmbedding]) -> None:
        """Persist dense embedding vectors for each chunk."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                for chunk_db_id, emb in zip(chunk_db_ids, embeddings):
                    vec_str = "[" + ",".join(str(v) for v in emb.vector) + "]"
                    cur.execute(
                        load("insert_chunk_embedding"),
                        (chunk_db_id, emb.model_id, emb.dim, vec_str),
                    )
        logger.info("saved embeddings count=%d model=%s", len(embeddings),
                    embeddings[0].model_id if embeddings else "—")

    def check_embed_compat(self, model_id: str, dim: int) -> None:
        """Fail-closed startup check: raise if stored model/dim differs from configured."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_embedding_model"))
                row = cur.fetchone()
        if row is None:
            return
        stored_model, stored_dim = row[0], int(row[1])
        if stored_model != model_id or stored_dim != dim:
            raise RuntimeError(
                f"embed model mismatch: stored=({stored_model}, {stored_dim}) "
                f"configured=({model_id}, {dim}). Re-embed or update config."
            )

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
