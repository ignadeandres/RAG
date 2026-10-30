"""Ranking metrics over document rankings with graded relevance."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from roboost_rag.domain import RetrievedChunk


def document_ranking(chunks: Sequence[RetrievedChunk]) -> list[str]:
    """Document paths in chunk order, each counted at its first appearance only."""
    return list(dict.fromkeys(c.document_path for c in chunks))


def reciprocal_rank(ranking: Sequence[str], grades: Mapping[str, int], k: int) -> float:
    """1 / position of the first relevant document within the top k; 0 if none."""
    for position, doc in enumerate(ranking[:k], start=1):
        if grades.get(doc, 0) > 0:
            return 1.0 / position
    return 0.0


def _dcg(gains: Sequence[int]) -> float:
    return sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(gains, start=1))


def ndcg(ranking: Sequence[str], grades: Mapping[str, int], k: int) -> float:
    """nDCG@k with gain 2^grade - 1, normalised by the ideal order of the labelled grades."""
    ideal = _dcg(sorted((g for g in grades.values() if g > 0), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return _dcg([grades.get(doc, 0) for doc in ranking[:k]]) / ideal
