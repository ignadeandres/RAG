"""Reciprocal Rank Fusion of several ranked result lists."""

from __future__ import annotations

from collections.abc import Sequence

from roboost_rag.domain import RetrievedChunk


def reciprocal_rank_fusion(
    ranked_lists: Sequence[tuple[Sequence[RetrievedChunk], float]],
    *,
    k: int = 60,
    limit: int = 10,
) -> list[RetrievedChunk]:
    """Fuse `(results, weight)` lists by rank: score(d) = Σ weight / (k + rank).

    Ranks are 1-based. The returned chunks carry the fused score.
    """
    scores: dict[int, float] = {}
    chunks: dict[int, RetrievedChunk] = {}
    for results, weight in ranked_lists:
        for rank, chunk in enumerate(results, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + weight / (k + rank)
            chunks.setdefault(chunk.chunk_id, chunk)
    best = sorted(scores, key=lambda cid: -scores[cid])[:limit]
    return [chunks[cid].model_copy(update={"score": scores[cid]}) for cid in best]
