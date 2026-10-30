"""In-memory fakes of every port, for unit tests."""

from __future__ import annotations

import math
from collections.abc import Sequence
from contextlib import contextmanager

from roboost_rag.domain import Chunk, Document, RetrievedChunk, Role
from roboost_rag.ports import LLMUnavailableError, LoadResult, RerankerError


class FakeSource:
    def __init__(self, documents: list[Document] | None = None, failed: list[str] | None = None):
        self.documents = documents or []
        self.failed = failed or []

    def load(self) -> LoadResult:
        return LoadResult(list(self.documents), list(self.failed))


class FakeEmbedder:
    """Deterministic bag-of-letters embedding; can be told to fail."""

    def __init__(self, fail_on: str | None = None):
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail_on and any(self.fail_on in t for t in texts):
            raise RuntimeError("embedding failed")
        return [self._vector(t) for t in texts]

    @staticmethod
    def _vector(text: str) -> list[float]:
        vec = [0.0] * 26
        for ch in text.lower():
            if "a" <= ch <= "z":
                vec[ord(ch) - 97] += 1
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FakeStore:
    """Implements VectorStore and LexicalIndex in memory, honouring the role filter."""

    def __init__(self):
        self.documents: dict[str, Document] = {}
        self.rows: list[tuple[RetrievedChunk, list[float]]] = []
        self.locked = False
        self._next_id = 1

    def indexed_hashes(self) -> dict[str, str]:
        return {p: d.content_hash for p, d in self.documents.items()}

    def replace_document(self, document, chunks: Sequence[Chunk], embeddings) -> None:
        self.delete_document(document.path)
        self.documents[document.path] = document
        for chunk, emb in zip(chunks, embeddings, strict=True):
            row = RetrievedChunk(
                chunk_id=self._next_id,
                document_path=document.path,
                title=document.title,
                content=chunk.content,
                access_level=document.access_level,
                score=0.0,
            )
            self._next_id += 1
            self.rows.append((row, list(emb)))

    def delete_document(self, path: str) -> None:
        self.documents.pop(path, None)
        self.rows = [(r, e) for r, e in self.rows if r.document_path != path]

    def _visible(self, role: Role):
        return [(r, e) for r, e in self.rows if r.access_level <= role.clearance]

    def search_vector(self, embedding, role: Role, limit: int) -> list[RetrievedChunk]:
        scored = [
            r.model_copy(update={"score": sum(a * b for a, b in zip(e, embedding))})
            for r, e in self._visible(role)
        ]
        return sorted(scored, key=lambda r: -r.score)[:limit]

    def search_lexical(self, query: str, role: Role, limit: int) -> list[RetrievedChunk]:
        terms = {t for t in query.lower().split() if t}
        scored = []
        for r, _ in self._visible(role):
            hits = sum(1 for t in terms if t in r.content.lower())
            if hits:
                scored.append(r.model_copy(update={"score": float(hits)}))
        return sorted(scored, key=lambda r: -r.score)[:limit]

    @contextmanager
    def sync_lock(self):
        if self.locked:
            yield False
            return
        self.locked = True
        try:
            yield True
        finally:
            self.locked = False


class FakeReranker:
    """Scores by a fixed mapping chunk_id -> score, or fails."""

    def __init__(self, scores: dict[int, float] | None = None, fail: bool = False):
        self.scores = scores or {}
        self.fail = fail
        self.calls: list[list[RetrievedChunk]] = []

    def rerank(self, query, chunks, top_n):
        self.calls.append(list(chunks))
        if self.fail:
            raise RerankerError("reranker down")
        scored = [c.model_copy(update={"score": self.scores.get(c.chunk_id, 0.0)}) for c in chunks]
        return sorted(scored, key=lambda c: -c.score)[:top_n]


class FakeLLM:
    def __init__(self, reply: str = "Respuesta [1]", fail: bool = False):
        self.reply = reply
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if self.fail:
            raise LLMUnavailableError("ollama down")
        return self.reply
