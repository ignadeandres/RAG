"""Embedder backed by a local Ollama server (default model: bge-m3, 1024 dimensions)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence

import ollama

from roboost_rag.adapters.ollama_llm import missing_model_message

log = logging.getLogger(__name__)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, ollama.ResponseError):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


class OllamaEmbedder:
    def __init__(
        self,
        host: str,
        model: str = "bge-m3",
        *,
        dimensions: int = 1024,
        batch_size: int = 32,
        max_retries: int = 5,
        base_delay: float = 1.0,
        timeout: float = 120.0,
        client: ollama.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.host = host
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.client = client or ollama.Client(host=host, timeout=timeout)
        self.sleep = sleep

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_batch(list(texts[i : i + self.batch_size])))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        for attempt in range(self.max_retries + 1):
            try:
                vectors = [list(v) for v in self.client.embed(model=self.model, input=batch).embeddings]
                break
            except Exception as exc:
                if not _is_transient(exc) or attempt == self.max_retries:
                    raise
                delay = self.base_delay * 2**attempt
                log.warning("Error transitorio de Ollama (%s); reintento en %.1fs", exc, delay)
                self.sleep(delay)
        if any(len(v) != self.dimensions for v in vectors):
            raise ValueError(
                f"El modelo {self.model} devuelve vectores de {len(vectors[0])} dimensiones; "
                f"el esquema espera {self.dimensions}"
            )
        return vectors

    def check_model(self) -> str | None:
        return missing_model_message(self.client, self.host, self.model)
