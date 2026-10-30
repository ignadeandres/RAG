import math

import pytest

from roboost_rag.services.metrics import document_ranking, ndcg, reciprocal_rank
from tests.test_retrieval import rc


def test_document_ranking_keeps_first_appearance():
    chunks = [rc(1), rc(2), rc(1), rc(3)]
    chunks[2] = chunks[2].model_copy(update={"chunk_id": 9})  # second chunk of d1.md
    assert document_ranking(chunks) == ["d1.md", "d2.md", "d3.md"]


def test_reciprocal_rank_third_position():
    assert reciprocal_rank(["x", "y", "a"], {"a": 1}, k=4) == pytest.approx(1 / 3)


def test_reciprocal_rank_outside_cutoff_or_missing():
    ranking = ["x", "y", "z", "w", "a"]
    assert reciprocal_rank(ranking, {"a": 2}, k=4) == 0.0
    assert reciprocal_rank(ranking, {"a": 2}, k=10) == pytest.approx(1 / 5)
    assert reciprocal_rank(ranking, {"missing": 2}, k=10) == 0.0


def test_ndcg_ideal_order_is_one():
    assert ndcg(["a", "b", "x"], {"a": 2, "b": 1}, k=10) == pytest.approx(1.0)


def test_ndcg_inverted_grades_by_hand():
    # DCG = (2^1-1)/log2(2) + (2^2-1)/log2(3) = 1 + 3/1.585; IDCG = 3 + 1/1.585
    expected = (1 + 3 / math.log2(3)) / (3 + 1 / math.log2(3))
    assert ndcg(["b", "a"], {"a": 2, "b": 1}, k=10) == pytest.approx(expected)
    assert expected == pytest.approx(0.7967, abs=1e-4)


def test_ndcg_penalises_missing_relevant_document():
    # Only 'a' retrieved; 'b' (grade 1) missing → below 1.
    assert ndcg(["a", "x"], {"a": 2, "b": 1}, k=10) == pytest.approx(3 / (3 + 1 / math.log2(3)))


def test_ndcg_cutoff():
    assert ndcg(["x", "y", "a"], {"a": 1}, k=2) == 0.0
    assert ndcg(["x", "y", "a"], {"a": 1}, k=3) == pytest.approx(1 / 2)  # 1/log2(4)


def test_ndcg_without_relevant_labels_is_zero():
    assert ndcg(["a"], {}, k=10) == 0.0
