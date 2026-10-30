from types import SimpleNamespace

import ollama
import pytest

from roboost_rag.adapters.ollama_embedder import OllamaEmbedder


class FakeClient:
    def __init__(self, failures=(), dims=1024):
        self.failures = list(failures)
        self.dims = dims
        self.calls = []

    def embed(self, model, input):
        self.calls.append((model, list(input)))
        if self.failures:
            raise self.failures.pop(0)
        return SimpleNamespace(embeddings=[[float(i)] * self.dims for i in range(len(input))])

    def list(self):
        return SimpleNamespace(models=[SimpleNamespace(model="qwen3.5:9b")])


def make(client, **kw):
    sleeps = []
    return OllamaEmbedder("http://h:11434", client=client, sleep=sleeps.append, **kw), sleeps


def test_batches_with_bge_m3():
    client = FakeClient()
    emb, _ = make(client, batch_size=2)
    vectors = emb.embed(["a", "b", "c"])
    assert len(vectors) == 3 and all(len(v) == 1024 for v in vectors)
    assert client.calls == [("bge-m3", ["a", "b"]), ("bge-m3", ["c"])]


def test_retries_connection_and_server_errors():
    client = FakeClient(failures=[ConnectionError("refused"), ollama.ResponseError("busy", 503)])
    emb, sleeps = make(client)
    assert len(emb.embed(["a"])) == 1
    assert sleeps == [1.0, 2.0]


def test_gives_up_after_max_retries():
    client = FakeClient(failures=[ConnectionError("refused")] * 3)
    emb, sleeps = make(client, max_retries=2)
    with pytest.raises(ConnectionError):
        emb.embed(["a"])
    assert len(sleeps) == 2


def test_model_not_found_is_not_retried():
    client = FakeClient(failures=[ollama.ResponseError("model not found", 404)])
    emb, sleeps = make(client)
    with pytest.raises(ollama.ResponseError):
        emb.embed(["a"])
    assert sleeps == []


def test_wrong_dimensions_rejected():
    emb, _ = make(FakeClient(dims=768))
    with pytest.raises(ValueError, match="1024"):
        emb.embed(["a"])


def test_check_model_reports_missing_bge_m3():
    emb, _ = make(FakeClient())
    assert "ollama pull bge-m3" in emb.check_model()
