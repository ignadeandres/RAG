"""Composition root: the only place that knows the concrete adapters."""

from __future__ import annotations

import atexit
import logging
from dataclasses import dataclass

from roboost_rag.adapters.cohere_reranker import CohereReranker
from roboost_rag.adapters.fs_source import FileSystemSource
from roboost_rag.adapters.ollama_embedder import OllamaEmbedder
from roboost_rag.adapters.ollama_llm import OllamaLLM
from roboost_rag.adapters.openai_embedder import OpenAIEmbedder
from roboost_rag.adapters.paradedb_store import ParadeDBStore
from roboost_rag.config import Settings, load_settings
from roboost_rag.services.auth import UserDirectory
from roboost_rag.services.chunking import Chunker
from roboost_rag.services.ingestion import IngestionService
from roboost_rag.services.query import QueryService
from roboost_rag.services.retrieval import RetrievalConfig, RetrievalService
from roboost_rag.services.scheduler import SyncScheduler

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    store: ParadeDBStore
    ingestion: IngestionService
    scheduler: SyncScheduler
    retrieval: RetrievalService
    query: QueryService
    llm: OllamaLLM
    embedder: OllamaEmbedder | OpenAIEmbedder
    users: UserDirectory

    def startup_warnings(self) -> list[str]:
        warnings = []
        if problem := self.llm.check_model():
            warnings.append(problem)
        if isinstance(self.embedder, OllamaEmbedder) and (problem := self.embedder.check_model()):
            warnings.append(problem)
        if self.retrieval.reranker is None:
            warnings.append("COHERE_API_KEY no configurada: reranking desactivado.")
        for warning in warnings:
            log.warning(warning)
        return warnings


def build(settings: Settings | None = None) -> Container:
    s = settings or load_settings()
    store = ParadeDBStore(s.database_url)
    atexit.register(store.close)  # avoids pool-thread errors at interpreter shutdown
    embedder = _embedder(s)
    reranker = (
        CohereReranker(
            s.cohere_api_key.get_secret_value(), s.rerank_model, timeout=s.rerank_timeout_seconds
        )
        if s.cohere_api_key and s.cohere_api_key.get_secret_value()
        else None
    )
    if reranker is None:
        log.warning("COHERE_API_KEY no configurada: se usará el orden de la fusión sin reranking")

    ingestion = IngestionService(FileSystemSource(s.docs_dir), Chunker(s.chunk_size), embedder, store)
    retrieval = RetrievalService(
        embedder,
        store,
        store,
        reranker,
        RetrievalConfig(
            candidates_per_retriever=s.candidates_per_retriever,
            fusion_top=s.fusion_top,
            final_top_k=s.final_top_k,
            rrf_k=s.rrf_k,
            weight_vector=s.weight_vector,
            weight_bm25=s.weight_bm25,
            rerank_threshold=s.rerank_threshold,
        ),
    )
    llm = OllamaLLM(s.ollama_host, s.llm_model, temperature=s.llm_temperature)
    return Container(
        settings=s,
        store=store,
        ingestion=ingestion,
        scheduler=SyncScheduler(ingestion, store, s.reindex_interval_seconds),
        retrieval=retrieval,
        query=QueryService(retrieval, llm),
        llm=llm,
        embedder=embedder,
        users=UserDirectory(s.app_users),
    )


def _embedder(s: Settings) -> OllamaEmbedder | OpenAIEmbedder:
    if s.embedding_provider == "openai":
        return OpenAIEmbedder(
            s.openai_api_key.get_secret_value(),
            s.openai_embedding_model,
            dimensions=s.embedding_dimensions,
            batch_size=s.embedding_batch_size,
        )
    return OllamaEmbedder(
        s.ollama_host,
        s.embedding_model,
        dimensions=s.embedding_dimensions,
        batch_size=s.embedding_batch_size,
    )
