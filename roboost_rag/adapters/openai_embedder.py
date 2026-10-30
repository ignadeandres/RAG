"""Embedder backed by the OpenAI embeddings API, with batching and exponential backoff."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence

import openai

log = logging.getLogger(__name__)

TRANSIENT_ERRORS = (
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIConnectionError,  # includes APITimeoutError
)


class OpenAIEmbedder:
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        *,
        dimensions: int = 1024,
        batch_size: int = 100,
        max_retries: int = 5,
        base_delay: float = 1.0,
        client: openai.OpenAI | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        # The SDK's own retries are disabled so the backoff policy lives here.
        self.client = client or openai.OpenAI(api_key=api_key, max_retries=0)
        self.model = model
        self.dimensions = dimensions  # text-embedding-3-* can shorten vectors to fit the schema
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.sleep = sleep

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_batch(list(texts[i : i + self.batch_size])))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.embeddings.create(
                    model=self.model, input=batch, dimensions=self.dimensions
                )
                return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
            except TRANSIENT_ERRORS as exc:
                if attempt == self.max_retries:
                    raise
                delay = self.base_delay * 2**attempt
                log.warning("Error transitorio de OpenAI (%s); reintento en %.1fs", exc, delay)
                self.sleep(delay)
        raise AssertionError("unreachable")
