"""Evaluation of retrieval hit-rate (per mode) and of access-control leaks in answers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from roboost_rag.domain import Role
from roboost_rag.services.query import QueryService
from roboost_rag.services.retrieval import RetrievalService

# (label, retrieval mode, use reranker). Single retrievers are compared without the
# reranker; the full pipeline is hybrid + rerank.
RUNS = (
    ("vector", "vector", False),
    ("bm25", "bm25", False),
    ("hybrid (sin rerank)", "hybrid", False),
    ("hybrid + rerank", "hybrid", True),
)
FULL_PIPELINE = "hybrid + rerank"


@dataclass
class EvalResult:
    hit_rate: dict[str, float] = field(default_factory=dict)
    misses: dict[str, list[str]] = field(default_factory=dict)
    rerank_scores: list[tuple[str, bool, float]] = field(default_factory=list)  # (q, hit, best)
    leaks: list[str] = field(default_factory=list)
    denied_answers: list[tuple[str, str, str]] = field(default_factory=list)


def load_questions(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def evaluate_retrieval(
    retrieval: RetrievalService, questions: dict, *, pace_seconds: float = 0.0
) -> EvalResult:
    """`pace_seconds` spaces out reranked queries (Cohere trial keys allow 10 calls/minute)."""
    without_reranker = RetrievalService(
        retrieval.embedder, retrieval.vector_store, retrieval.lexical_index, None, retrieval.config
    )
    result = EvalResult()
    items = questions["answerable"]
    for label, mode, rerank in RUNS:
        if rerank and retrieval.reranker is None:
            continue
        service = retrieval if rerank else without_reranker
        hits, misses = 0, []
        for item in items:
            if rerank and pace_seconds:
                time.sleep(pace_seconds)
            chunks = service.retrieve(item["q"], Role(item["role"]), mode)
            found = {c.document_path for c in chunks}
            expected = set(item["expected"])
            ok = bool(found & expected) if expected else not found
            hits += ok
            if not ok:
                misses.append(f"[{item['role']}] {item['q']} -> {sorted(found)}")
            if rerank:
                result.rerank_scores.append(
                    (item["q"], bool(expected), max((c.score for c in chunks), default=0.0))
                )
        result.hit_rate[label] = hits / len(items)
        result.misses[label] = misses
    return result


def evaluate_denials(query: QueryService, questions: dict, result: EvalResult) -> EvalResult:
    for item in questions["denied"]:
        answer = query.ask(item["q"], Role(item["role"]))
        clearance = Role(item["role"]).clearance
        restricted = [s.path for s in answer.sources if s.access_level > clearance]
        leaked = [term for term in item["forbidden"] if term.lower() in answer.text.lower()]
        result.denied_answers.append((item["role"], item["q"], answer.text))
        if restricted or leaked:
            result.leaks.append(f"[{item['role']}] {item['q']}: fuentes={restricted} términos={leaked}")
    return result

