"""Ports: the interfaces services depend on. Adapters implement them."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from roboost_rag.domain import Chunk, Document, RetrievedChunk, Role


@dataclass
class LoadResult:
    documents: list[Document] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)  # paths that could not be read


@runtime_checkable
class DocumentSource(Protocol):
    def load(self) -> LoadResult: ...


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStore(Protocol):
    def indexed_hashes(self) -> dict[str, str]: ...

    def replace_document(
        self, document: Document, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]
    ) -> None:
        """Atomically replace every chunk of `document`."""
        ...

    def delete_document(self, path: str) -> None: ...

    def search_vector(
        self, embedding: Sequence[float], role: Role, limit: int
    ) -> list[RetrievedChunk]: ...

    def sync_lock(self) -> AbstractContextManager[bool]:
        """Try to take the exclusive sync lock; yields False if another sync holds it."""
        ...


@runtime_checkable
class LexicalIndex(Protocol):
    def search_lexical(self, query: str, role: Role, limit: int) -> list[RetrievedChunk]: ...


class RerankerError(RuntimeError):
    pass


@runtime_checkable
class Reranker(Protocol):
    def rerank(
        self, query: str, chunks: Sequence[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        """Return up to `top_n` chunks, best first, with `score` = relevance. Raises RerankerError."""
        ...


class LLMUnavailableError(RuntimeError):
    pass


@runtime_checkable
class LLM(Protocol):
    def generate(self, system: str, prompt: str) -> str:
        """Raises LLMUnavailableError if the model cannot be reached."""
        ...
