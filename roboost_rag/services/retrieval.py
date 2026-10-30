"""Hybrid retrieval: vector + BM25 (both role-filtered in the DB) → RRF → rerank → top-K."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from roboost_rag.domain import RetrievedChunk, Role
from roboost_rag.ports import Embedder, LexicalIndex, Reranker, RerankerError, VectorStore
from roboost_rag.services.fusion import reciprocal_rank_fusion

log = logging.getLogger(__name__)


class MissingRoleError(ValueError):
    pass


@dataclass(frozen=True)
class RetrievalConfig:
    candidates_per_retriever: int = 20
    fusion_top: int = 10
    final_top_k: int = 4
    rrf_k: int = 60
    weight_vector: float = 1.0
    weight_bm25: float = 1.0
    rerank_threshold: float = 0.04


class RetrievalService:
    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        lexical_index: LexicalIndex,
        reranker: Reranker | None,
        config: RetrievalConfig = RetrievalConfig(),
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.lexical_index = lexical_index
        self.reranker = reranker
        self.config = config
        self._pool = ThreadPoolExecutor(max_workers=2)

    def retrieve(
        self, question: str, role: Role | None, mode: str = "hybrid"
    ) -> list[RetrievedChunk]:
        """`mode` is hybrid (default), vector or bm25; the single-retriever modes exist for evaluation."""
        if not isinstance(role, Role):
            raise MissingRoleError("Una consulta debe ir asociada a un rol autenticado.")
        candidates = self.candidates(question, role, mode)
        if not candidates:
            return []
        return self._rerank(question, candidates)

    def candidates(self, question: str, role: Role, mode: str = "hybrid") -> list[RetrievedChunk]:
        """Fused top candidates (RRF order), before reranking."""
        n = self.config.candidates_per_retriever
        vector = lexical = None
        if mode in ("hybrid", "vector"):
            vector = self._pool.submit(self._vector_search, question, role, n)
        if mode in ("hybrid", "bm25"):
            lexical = self._pool.submit(self.lexical_index.search_lexical, question, role, n)
        lists = []
        if vector:
            lists.append((vector.result(), self.config.weight_vector))
        if lexical:
            lists.append((lexical.result(), self.config.weight_bm25))
        return reciprocal_rank_fusion(lists, k=self.config.rrf_k, limit=self.config.fusion_top)

    def _vector_search(self, question: str, role: Role, n: int) -> list[RetrievedChunk]:
        [embedding] = self.embedder.embed([question])
        return self.vector_store.search_vector(embedding, role, n)

    def _rerank(self, question: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        k = self.config.final_top_k
        if self.reranker is None:
            return candidates[:k]
        try:
            ranked = self.reranker.rerank(question, candidates, k)
        except RerankerError as exc:
            log.warning("Reranker no disponible, se usa el orden de la fusión: %s", exc)
            return candidates[:k]
        return self.select(ranked)

    def select(self, reranked: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Final selection from reranked chunks: drop those under the threshold, keep top-K."""
        threshold = self.config.rerank_threshold
        return [c for c in reranked if c.score >= threshold][: self.config.final_top_k]
