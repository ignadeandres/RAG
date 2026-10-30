"""Retrieval evaluation: ranking metrics before/after the reranker, hit-rate and access leaks."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

import yaml

from roboost_rag.domain import RetrievedChunk, Role
from roboost_rag.ports import RerankerError
from roboost_rag.services.metrics import document_ranking, ndcg, reciprocal_rank
from roboost_rag.services.query import QueryService
from roboost_rag.services.retrieval import RetrievalService

log = logging.getLogger(__name__)

# Ranking columns: single retrievers, hybrid in RRF order (before) and in reranker order (after).
VECTOR, BM25, BEFORE, AFTER = "vector", "bm25", "antes", "después"
CUTOFFS = (4, 10)
METRICS = tuple(f"{name}@{k}" for name in ("MRR", "nDCG") for k in CUTOFFS)
TIE_EPSILON = 1e-3
RETRY_DELAYS = (15.0, 30.0)  # seconds to wait before each retry of a failed rerank call


def grades_of(expected) -> dict[str, int]:
    """`expected` is a {path: grade} mapping or a list of paths (grade 1 each)."""
    if isinstance(expected, dict):
        return {path: int(grade) for path, grade in expected.items()}
    return dict.fromkeys(expected or [], 1)


def load_questions(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


@dataclass
class EvalResult:
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)  # column -> metric -> mean
    evaluated: int = 0  # in-domain questions included in the metrics
    excluded: list[str] = field(default_factory=list)  # reranker failed even after retries
    wins: list[str] = field(default_factory=list)
    ties: list[str] = field(default_factory=list)
    losses: list[str] = field(default_factory=list)
    hit_rate: dict[str, float] = field(default_factory=dict)  # "RRF top-K" and "sistema completo"
    misses: list[str] = field(default_factory=list)  # full-pipeline hit-rate failures
    out_of_domain: tuple[int, int] = (0, 0)  # (rejected, total)
    best_scores: list[tuple[str, bool, float]] = field(default_factory=list)  # calibration aid
    leaks: list[str] = field(default_factory=list)
    denied_answers: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def has_reranker(self) -> bool:
        return AFTER in self.metrics


def _scores(ranking: list[str], grades: dict[str, int]) -> dict[str, float]:
    out = {}
    for k in CUTOFFS:
        out[f"MRR@{k}"] = reciprocal_rank(ranking, grades, k)
        out[f"nDCG@{k}"] = ndcg(ranking, grades, k)
    return out


def _hit(chunks: list[RetrievedChunk], grades: dict[str, int]) -> bool:
    found = {c.document_path for c in chunks}
    relevant = {p for p, g in grades.items() if g > 0}
    return bool(found & relevant) if relevant else not found


class _Pacer:
    """Spaces out reranker calls (Cohere trial keys allow 10 calls per minute)."""

    def __init__(self, seconds: float, sleep: Callable[[float], None]):
        self.seconds, self.sleep, self.first = seconds, sleep, True

    def wait(self) -> None:
        if self.seconds and not self.first:
            self.sleep(self.seconds)
        self.first = False


def _rerank_all(
    retrieval: RetrievalService, question: str, candidates, pacer: _Pacer, sleep
) -> list[RetrievedChunk] | None:
    """Reranker order of every candidate (no threshold), or None if it keeps failing."""
    for delay in (0.0, *RETRY_DELAYS):
        if delay:
            sleep(delay)
        pacer.wait()
        try:
            return retrieval.reranker.rerank(question, candidates, len(candidates))
        except RerankerError as exc:
            log.warning("Reranker falló para %r: %s", question, exc)
    return None


def evaluate(
    retrieval: RetrievalService,
    questions: dict,
    *,
    pace_seconds: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> EvalResult:
    """One pass per question and at most one successful reranker call per question."""
    result = EvalResult()
    pacer = _Pacer(pace_seconds, sleep)
    k = retrieval.config.final_top_k
    per_column: dict[str, list[dict[str, float]]] = {}
    hits = {"RRF top-K": 0, "sistema completo": 0}
    answered = 0
    ood_rejected = ood_total = 0

    for item in questions["answerable"]:
        q, role, grades = item["q"], Role(item["role"]), grades_of(item["expected"])
        label = f"[{item['role']}] {q}"
        hybrid = retrieval.candidates(q, role, "hybrid")

        if retrieval.reranker is None or not hybrid:
            reranked = hybrid  # nothing to rerank: "after" equals "before"
            final = hybrid[:k] if retrieval.reranker is None else []
        else:
            reranked = _rerank_all(retrieval, q, hybrid, pacer, sleep)
            if reranked is None:
                result.excluded.append(label)
                continue
            final = retrieval.select(reranked)
            result.best_scores.append((label, bool(grades), reranked[0].score))

        answered += 1
        hits["RRF top-K"] += _hit(hybrid[:k], grades)
        if _hit(final, grades):
            hits["sistema completo"] += 1
        else:
            result.misses.append(f"{label} -> {document_ranking(final)}")

        if not grades:  # out of domain: no ranking metrics, only rejection
            ood_total += 1
            ood_rejected += not final
            continue

        rankings = {
            VECTOR: document_ranking(retrieval.candidates(q, role, "vector")),
            BM25: document_ranking(retrieval.candidates(q, role, "bm25")),
            BEFORE: document_ranking(hybrid),
        }
        if retrieval.reranker is not None:
            rankings[AFTER] = document_ranking(reranked)
        scores = {col: _scores(r, grades) for col, r in rankings.items()}
        for col, s in scores.items():
            per_column.setdefault(col, []).append(s)
        if AFTER in scores:
            delta = scores[AFTER]["nDCG@10"] - scores[BEFORE]["nDCG@10"]
            bucket = result.ties if abs(delta) < TIE_EPSILON else (
                result.wins if delta > 0 else result.losses
            )
            bucket.append(f"{label} (Δ nDCG@10 = {delta:+.3f})")

    result.evaluated = len(per_column.get(BEFORE, []))
    result.metrics = {
        col: {m: mean(s[m] for s in rows) for m in METRICS} for col, rows in per_column.items()
    }
    if answered:
        result.hit_rate = {name: n / answered for name, n in hits.items()}
    result.out_of_domain = (ood_rejected, ood_total)
    return result


def evaluate_denials(
    query: QueryService,
    questions: dict,
    result: EvalResult,
    *,
    pace_seconds: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> EvalResult:
    pacer = _Pacer(pace_seconds, sleep)
    for item in questions["denied"]:
        pacer.wait()
        answer = query.ask(item["q"], Role(item["role"]))
        clearance = Role(item["role"]).clearance
        restricted = [s.path for s in answer.sources if s.access_level > clearance]
        leaked = [term for term in item["forbidden"] if term.lower() in answer.text.lower()]
        result.denied_answers.append((item["role"], item["q"], answer.text))
        if restricted or leaked:
            result.leaks.append(f"[{item['role']}] {item['q']}: fuentes={restricted} términos={leaked}")
    return result
