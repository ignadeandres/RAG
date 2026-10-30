"""VectorStore + LexicalIndex on ParadeDB (PostgreSQL with pgvector and pg_search).

The role filter is always part of the search SQL, so unauthorised chunks never
leave the database.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import numpy as np
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from roboost_rag.domain import AccessLevel, Chunk, Document, RetrievedChunk, Role

SYNC_LOCK_KEY = 0x524F424F  # arbitrary, constant across processes

_SELECT = """
    SELECT c.id, d.path, d.title, c.content, c.access_level, {score} AS score
    FROM chunks c JOIN documents d ON d.id = c.document_id
"""

_VECTOR_SQL = (
    _SELECT.format(score="1 - (c.embedding <=> %(q)s)")
    + """
    WHERE c.access_level <= %(rank)s
    ORDER BY c.embedding <=> %(q)s
    LIMIT %(limit)s
"""
)

_LEXICAL_SQL = (
    _SELECT.format(score="pdb.score(c.id)")
    + """
    WHERE c.content ||| %(q)s AND c.access_level <= %(rank)s
    ORDER BY pdb.score(c.id) DESC
    LIMIT %(limit)s
"""
)


def _to_chunk(row) -> RetrievedChunk:
    chunk_id, path, title, content, level, score = row
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_path=path,
        title=title,
        content=content,
        access_level=AccessLevel(level),
        score=float(score),
    )


class ParadeDBStore:
    def __init__(self, dsn: str, *, ef_search: int = 100, pool_size: int = 5):
        self.ef_search = ef_search
        self.pool = ConnectionPool(
            dsn, min_size=1, max_size=pool_size, configure=register_vector, open=True
        )

    def close(self) -> None:
        self.pool.close()

    def indexed_hashes(self) -> dict[str, str]:
        with self.pool.connection() as conn:
            return dict(conn.execute("SELECT path, content_hash FROM documents").fetchall())

    def replace_document(
        self, document: Document, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]
    ) -> None:
        with self.pool.connection() as conn, conn.transaction():
            (doc_id,) = conn.execute(
                """
                INSERT INTO documents (path, title, access_level, content_hash)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (path) DO UPDATE SET
                    title = EXCLUDED.title,
                    access_level = EXCLUDED.access_level,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = now()
                RETURNING id
                """,
                (document.path, document.title, int(document.access_level), document.content_hash),
            ).fetchone()
            conn.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO chunks (document_id, position, content, access_level, embedding)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            doc_id,
                            chunk.position,
                            chunk.content,
                            int(document.access_level),
                            np.asarray(emb, dtype=np.float32),
                        )
                        for chunk, emb in zip(chunks, embeddings, strict=True)
                    ],
                )

    def delete_document(self, path: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM documents WHERE path = %s", (path,))

    def search_vector(
        self, embedding: Sequence[float], role: Role, limit: int
    ) -> list[RetrievedChunk]:
        with self.pool.connection() as conn, conn.transaction():
            # iterative_scan keeps walking the HNSW graph until `limit` rows pass the filter.
            conn.execute(f"SET LOCAL hnsw.ef_search = {int(self.ef_search)}")
            conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            rows = conn.execute(
                _VECTOR_SQL,
                {
                    "q": np.asarray(embedding, dtype=np.float32),
                    "rank": int(role.clearance),
                    "limit": limit,
                },
            ).fetchall()
        # relaxed_order may return rows slightly out of order.
        return sorted(map(_to_chunk, rows), key=lambda c: -c.score)

    def search_lexical(self, query: str, role: Role, limit: int) -> list[RetrievedChunk]:
        # `|||` tokenizes the text with the field's tokenizer (no query-parser syntax),
        # so user input needs no escaping; skip queries with no searchable token.
        if not re.search(r"\w", query):
            return []
        with self.pool.connection() as conn:
            rows = conn.execute(
                _LEXICAL_SQL, {"q": query, "rank": int(role.clearance), "limit": limit}
            ).fetchall()
        return [_to_chunk(row) for row in rows]

    @contextmanager
    def sync_lock(self) -> Iterator[bool]:
        with self.pool.connection() as conn:
            conn.autocommit = True
            (acquired,) = conn.execute(
                "SELECT pg_try_advisory_lock(%s)", (SYNC_LOCK_KEY,)
            ).fetchone()
            try:
                yield acquired
            finally:
                if acquired:
                    conn.execute("SELECT pg_advisory_unlock(%s)", (SYNC_LOCK_KEY,))
                conn.autocommit = False
