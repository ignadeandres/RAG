"""Reranker backed by the Cohere Rerank API."""

from __future__ import annotations

from collections.abc import Sequence

import cohere

from roboost_rag.domain import RetrievedChunk
from roboost_rag.ports import RerankerError


class CohereReranker:
    def __init__(
        self,
        api_key: str,
        model: str = "rerank-v3.5",
        *,
        timeout: float = 5.0,
        client: cohere.ClientV2 | None = None,
    ):
        self.client = client or cohere.ClientV2(api_key=api_key, timeout=timeout)
        self.model = model

    def rerank(
        self, query: str, chunks: Sequence[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        try:
            response = self.client.rerank(
                model=self.model,
                query=query,
                documents=[c.content for c in chunks],
                top_n=min(top_n, len(chunks)),
            )
        except Exception as exc:  # network, timeout, auth, quota...
            raise RerankerError(f"Cohere rerank failed: {_describe(exc)}") from exc
        ranked = sorted(response.results, key=lambda r: -r.relevance_score)
        return [
            chunks[r.index].model_copy(update={"score": float(r.relevance_score)})
            for r in ranked[:top_n]
        ]


def _describe(exc: Exception) -> str:
    """Short error description (SDK errors otherwise include every response header)."""
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    message = body.get("message") if isinstance(body, dict) else None
    if status:
        return f"HTTP {status}: {message or type(exc).__name__}"
    return f"{type(exc).__name__}: {exc}"
