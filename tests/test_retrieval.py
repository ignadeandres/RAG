from types import SimpleNamespace

import pytest

from roboost_rag.adapters.cohere_reranker import CohereReranker
from roboost_rag.domain import AccessLevel, Chunk, Document, RetrievedChunk, Role
from roboost_rag.ports import RerankerError
from roboost_rag.services.fusion import reciprocal_rank_fusion
from roboost_rag.services.retrieval import MissingRoleError, RetrievalConfig, RetrievalService
from tests.fakes import FakeEmbedder, FakeReranker, FakeStore


def rc(cid: int, level=AccessLevel.PUBLIC) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid, document_path=f"d{cid}.md", title=f"T{cid}",
        content=f"chunk {cid}", access_level=level, score=0.0,
    )


# --- RRF -----------------------------------------------------------------

def test_rrf_chunk_in_both_lists_ranks_first():
    vector = [rc(1), rc(2), rc(3)]
    bm25 = [rc(4), rc(2), rc(5)]
    fused = reciprocal_rank_fusion([(vector, 1.0), (bm25, 1.0)])
    assert fused[0].chunk_id == 2
    assert len({c.chunk_id for c in fused}) == len(fused) == 5


def test_rrf_one_empty_list_keeps_other_order():
    fused = reciprocal_rank_fusion([([rc(1), rc(2)], 1.0), ([], 1.0)])
    assert [c.chunk_id for c in fused] == [1, 2]


def test_rrf_both_empty():
    assert reciprocal_rank_fusion([([], 1.0), ([], 1.0)]) == []


def test_rrf_limit_and_weights():
    vector = [rc(i) for i in range(1, 16)]
    bm25 = [rc(i) for i in range(100, 115)]
    fused = reciprocal_rank_fusion([(vector, 1.0), (bm25, 2.0)], limit=10)
    assert len(fused) == 10
    assert fused[0].chunk_id == 100  # heavier BM25 weight wins ties at equal rank


# --- Cohere adapter --------------------------------------------------------

class FakeCohereClient:
    def __init__(self, scores=None, fail=False):
        self.scores, self.fail, self.calls = scores or [], fail, []

    def rerank(self, model, query, documents, top_n):
        self.calls.append(SimpleNamespace(model=model, documents=documents, top_n=top_n))
        if self.fail:
            raise TimeoutError("timeout")
        results = [SimpleNamespace(index=i, relevance_score=s) for i, s in enumerate(self.scores)]
        return SimpleNamespace(results=results)


def test_cohere_orders_descending_and_cuts_top_k():
    client = FakeCohereClient(scores=[0.1, 0.9, 0.5])
    rr = CohereReranker("k", model="rerank-x", client=client)
    out = rr.rerank("q", [rc(1), rc(2), rc(3)], top_n=2)
    assert [(c.chunk_id, c.score) for c in out] == [(2, 0.9), (3, 0.5)]
    assert client.calls[0].model == "rerank-x"
    assert client.calls[0].documents == ["chunk 1", "chunk 2", "chunk 3"]


def test_cohere_error_becomes_reranker_error():
    rr = CohereReranker("k", client=FakeCohereClient(fail=True))
    with pytest.raises(RerankerError):
        rr.rerank("q", [rc(1)], top_n=1)


def test_cohere_http_error_message_is_short():
    class RateLimited(Exception):
        status_code = 429
        body = {"message": "Trial key limited to 10 API calls / minute"}

    class Client(FakeCohereClient):
        def rerank(self, **kw):
            raise RateLimited({"huge": "headers"})

    with pytest.raises(RerankerError) as exc:
        CohereReranker("k", client=Client()).rerank("q", [rc(1)], top_n=1)
    assert str(exc.value) == "Cohere rerank failed: HTTP 429: Trial key limited to 10 API calls / minute"


# --- RetrievalService ------------------------------------------------------

def indexed_store():
    store, embedder = FakeStore(), FakeEmbedder()
    docs = [
        ("vacaciones.md", AccessLevel.PUBLIC, "vacaciones dias laborables solicitud"),
        ("prl.md", AccessLevel.PUBLIC, "procedimiento evacuacion prl04 emergencia"),
        ("bandas.md", AccessLevel.HR_MANAGER, "bandas salariales senior engineer"),
        ("atlas.md", AccessLevel.ADMIN, "proyecto atlas reestructuracion"),
    ]
    for path, level, text in docs:
        d = Document(path=path, title=path, access_level=level, body=text,
                     content_hash=path, body_hash=path)
        store.replace_document(d, [Chunk(position=0, content=text)], embedder.embed([text]))
    return store, embedder


def make_service(reranker=None, **cfg):
    store, embedder = indexed_store()
    return RetrievalService(embedder, store, store, reranker, RetrievalConfig(**cfg)), store


def test_rejects_query_without_role():
    svc, _ = make_service()
    with pytest.raises(MissingRoleError):
        svc.retrieve("vacaciones", None)


def test_role_filter_applies_to_both_retrievers():
    reranker = FakeReranker()
    svc, _ = make_service(reranker, rerank_threshold=0.0)
    svc.retrieve("proyecto atlas bandas salariales", Role.PUBLIC)
    sent = reranker.calls[0]
    assert sent and all(c.access_level is AccessLevel.PUBLIC for c in sent)


def test_empty_index_for_role_returns_empty():
    svc = RetrievalService(FakeEmbedder(), FakeStore(), FakeStore(), FakeReranker())
    assert svc.retrieve("vacaciones", Role.ADMIN) == []


def test_reranker_scores_and_threshold():
    svc, store = make_service(FakeReranker(scores={1: 0.95, 2: 0.05}), rerank_threshold=0.1)
    out = svc.retrieve("vacaciones evacuacion", Role.PUBLIC)
    assert [c.chunk_id for c in out] == [1]


def test_nothing_above_threshold_returns_empty():
    svc, _ = make_service(FakeReranker(scores={}), rerank_threshold=0.1)
    assert svc.retrieve("receta de paella", Role.ADMIN) == []


def test_reranker_down_falls_back_to_fusion_order_without_threshold():
    svc, _ = make_service(FakeReranker(fail=True), final_top_k=2, rerank_threshold=0.99)
    out = svc.retrieve("vacaciones", Role.ADMIN)
    assert len(out) == 2
    assert out[0].document_path == "vacaciones.md"


def test_no_reranker_configured_uses_fusion_order():
    svc, _ = make_service(None, final_top_k=3)
    assert len(svc.retrieve("vacaciones", Role.ADMIN)) == 3


def test_lexical_term_found_through_hybrid():
    svc, _ = make_service(None, final_top_k=1)
    [top] = svc.retrieve("prl04", Role.PUBLIC)
    assert top.document_path == "prl.md"
