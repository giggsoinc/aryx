-- Inc 9: document + vector plane.
-- pgvector extension, document metadata, text chunks, and dense embeddings.
-- Embedding dim is 768 (nomic-embed-text via Ollama broker config).
-- Idempotent; never edit earlier migrations.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS aryx_document (
    id           BIGSERIAL PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    file_name    TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    byte_count   BIGINT NOT NULL DEFAULT 0,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS aryx_chunk (
    id          BIGSERIAL PRIMARY KEY,
    doc_id      BIGINT NOT NULL REFERENCES aryx_document (id),
    chunk_index INTEGER NOT NULL,
    page_slide  INTEGER,
    char_start  INTEGER NOT NULL DEFAULT 0,
    char_end    INTEGER NOT NULL DEFAULT 0,
    text        TEXT NOT NULL,
    UNIQUE (doc_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunk_doc ON aryx_chunk (doc_id);

CREATE TABLE IF NOT EXISTS aryx_chunk_embedding (
    id          BIGSERIAL PRIMARY KEY,
    chunk_id    BIGINT NOT NULL REFERENCES aryx_chunk (id),
    model_id    TEXT NOT NULL,
    dim         INTEGER NOT NULL,
    embedding   vector(768),
    embedded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chunk_id, model_id)
);
