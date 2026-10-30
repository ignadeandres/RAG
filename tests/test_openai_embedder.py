from types import SimpleNamespace

import httpx2
import openai
import pytest

from roboost_rag.adapters.openai_embedder import OpenAIEmbedder

REQ = httpx2.Request("POST", "https://api.openai.com/v1/embeddings")


def rate_limited():
    return openai.RateLimitError("rate", response=httpx2.Response(429, request=REQ), body=None)


def server_error():
    return openai.InternalServerError("down", response=httpx2.Response(503, request=REQ), body=None)


class FakeClient:
    def __init__(self, failures=()):
        self.failures = list(failures)
        self.calls = []
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, model, input, dimensions):
        self.calls.append((model, list(input)))
        self.dimensions = dimensions
        if self.failures:
            raise self.failures.pop(0)
        # Return items out of order to check they are re-sorted by index.
        data = [SimpleNamespace(index=i, embedding=[float(i)]) for i in range(len(input))]
        return SimpleNamespace(data=list(reversed(data)))


def make(client, **kw):
    sleeps = []
    emb = OpenAIEmbedder("k", client=client, sleep=sleeps.append, **kw)
    return emb, sleeps


def test_batches_and_preserves_order():
    client = FakeClient()
    emb, _ = make(client, batch_size=2)
    assert emb.embed(["a", "b", "c"]) == [[0.0], [1.0], [0.0]]
    assert [c[1] for c in client.calls] == [["a", "b"], ["c"]]
    assert client.calls[0][0] == "text-embedding-3-small"
    assert client.dimensions == 1024


def test_retries_transient_errors_with_exponential_backoff():
    client = FakeClient(failures=[rate_limited(), server_error()])
    emb, sleeps = make(client, base_delay=1.0)
    assert emb.embed(["a"]) == [[0.0]]
    assert sleeps == [1.0, 2.0]


def test_gives_up_after_max_retries():
    client = FakeClient(failures=[rate_limited()] * 4)
    emb, sleeps = make(client, max_retries=3)
    with pytest.raises(openai.RateLimitError):
        emb.embed(["a"])
    assert len(client.calls) == 4
    assert len(sleeps) == 3


def test_non_transient_error_is_not_retried():
    bad = openai.BadRequestError("bad", response=httpx2.Response(400, request=REQ), body=None)
    client = FakeClient(failures=[bad])
    emb, sleeps = make(client)
    with pytest.raises(openai.BadRequestError):
        emb.embed(["a"])
    assert sleeps == []
