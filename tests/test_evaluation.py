from pathlib import Path

import pytest

from roboost_rag.cli import format_report
from roboost_rag.domain import Role
from roboost_rag.services.evaluation import (
    AFTER,
    BEFORE,
    RETRY_DELAYS,
    evaluate,
    grades_of,
    load_questions,
)
from roboost_rag.services.retrieval import RetrievalConfig, RetrievalService
from tests.fakes import FakeReranker
from tests.test_retrieval import indexed_store

# indexed_store() chunk ids: 1 vacaciones.md, 2 prl.md, 3 bandas.md, 4 atlas.md
QUESTIONS = {
    "answerable": [
        {"role": "admin", "q": "vacaciones prl04", "expected": {"prl.md": 2, "vacaciones.md": 1}},
        {"role": "admin", "q": "bandas salariales", "expected": ["bandas.md"]},
        {"role": "admin", "q": "receta de paella", "expected": []},
    ],
    "denied": [],
}


class QueryReranker(FakeReranker):
    """Scores per (question, chunk id), like a real reranker; 0 when unlisted."""

    def __init__(self, scores_by_query):
        super().__init__()
        self.scores_by_query = scores_by_query

    def rerank(self, query, chunks, top_n):
        self.scores = self.scores_by_query.get(query, {})
        return super().rerank(query, chunks, top_n)


GOOD = QueryReranker({
    "vacaciones prl04": {2: 0.9, 1: 0.5},
    "bandas salariales": {3: 0.8},
})


def service(reranker, **cfg):
    store, embedder = indexed_store()
    return RetrievalService(embedder, store, store, reranker, RetrievalConfig(**cfg))


def test_grades_from_dict_or_list():
    assert grades_of({"a.md": 2, "b.md": 1}) == {"a.md": 2, "b.md": 1}
    assert grades_of(["a.md", "b.md"]) == {"a.md": 1, "b.md": 1}
    assert grades_of([]) == {}


def test_one_reranker_call_per_question_with_the_same_candidates():
    reranker = GOOD
    reranker.calls.clear()
    retrieval = service(reranker, rerank_threshold=0.04)
    evaluate(retrieval, QUESTIONS)
    assert len(reranker.calls) == 3
    for (q, sent) in zip(QUESTIONS["answerable"], reranker.calls):
        fused = retrieval.candidates(q["q"], Role(q["role"]), "hybrid")
        assert [c.chunk_id for c in sent] == [c.chunk_id for c in fused]


def test_reranker_reorders_and_metrics_reflect_it():
    result = evaluate(service(GOOD, rerank_threshold=0.04), QUESTIONS)
    assert result.evaluated == 2  # the out-of-domain question has no ranking metrics
    assert result.metrics[AFTER]["MRR@4"] == pytest.approx(1.0)
    assert result.metrics[AFTER]["nDCG@10"] == pytest.approx(1.0)
    assert result.metrics[AFTER]["nDCG@10"] >= result.metrics[BEFORE]["nDCG@10"]
    assert len(result.wins) + len(result.ties) + len(result.losses) == 2


def test_out_of_domain_rejected_by_threshold():
    result = evaluate(service(GOOD, rerank_threshold=0.04), QUESTIONS)  # paella scores 0
    assert result.out_of_domain == (1, 1)
    assert result.hit_rate["sistema completo"] == pytest.approx(1.0)


def test_failing_reranker_excludes_questions_after_retries():
    sleeps = []
    reranker = FakeReranker(fail=True)
    result = evaluate(service(reranker), QUESTIONS, sleep=sleeps.append)
    assert len(result.excluded) == 3
    assert len(reranker.calls) == 3 * (1 + len(RETRY_DELAYS))
    assert sleeps == list(RETRY_DELAYS) * 3
    assert result.evaluated == 0


def test_reranker_calls_are_paced():
    sleeps = []
    evaluate(service(FakeReranker(scores={2: 0.9})), QUESTIONS, pace_seconds=6.5, sleep=sleeps.append)
    assert sleeps == [6.5, 6.5]  # between the 3 calls, not before the first


def test_without_reranker_only_before_columns():
    result = evaluate(service(None), QUESTIONS)
    assert AFTER not in result.metrics and BEFORE in result.metrics
    assert not result.has_reranker
    assert result.out_of_domain == (0, 1)  # no threshold without reranker


def test_report_shows_delta_and_counts():
    result = evaluate(service(GOOD), QUESTIONS)
    report = format_report(result, verbose=True)
    assert "Δ rerank" in report and "nDCG@10" in report and "MRR@4" in report
    assert "fuera de dominio rechazadas: 1/1" in report


def test_eval_set_paths_exist():
    root = Path(__file__).resolve().parents[1]
    questions = load_questions(root / "tests/eval/questions.yaml")
    for item in questions["answerable"]:
        for path in grades_of(item["expected"]):
            assert (root / "docs" / path).is_file(), path
