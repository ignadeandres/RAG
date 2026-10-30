-- Schema for the ROBOOST HR RAG index (ParadeDB 0.26: pgvector + pg_search).
-- access_level is an ordinal: 0 = public, 1 = hr_manager, 2 = admin.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;

CREATE TABLE IF NOT EXISTS documents (
    id            BIGSERIAL PRIMARY KEY,
    path          TEXT        NOT NULL UNIQUE,
    title         TEXT        NOT NULL,
    access_level  SMALLINT    NOT NULL CHECK (access_level BETWEEN 0 AND 2),
    content_hash  TEXT        NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id            BIGSERIAL PRIMARY KEY,
    document_id   BIGINT      NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    position      INTEGER     NOT NULL,
    content       TEXT        NOT NULL,
    access_level  SMALLINT    NOT NULL CHECK (access_level BETWEEN 0 AND 2),
    embedding     vector(1024) NOT NULL,
    UNIQUE (document_id, position)
);

-- Semantic search.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- Lexical BM25 search: Spanish stemming and accent folding; access_level indexed
-- so the role filter is evaluated inside the BM25 index.
CREATE INDEX IF NOT EXISTS chunks_bm25
    ON chunks USING paradedb (
        id,
        (content::pdb.simple('stemmer=spanish', 'ascii_folding=true')),
        access_level
    );
