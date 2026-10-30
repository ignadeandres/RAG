from types import SimpleNamespace

import pytest

from roboost_rag.adapters.ollama_llm import OllamaLLM
from roboost_rag.domain import Role
from roboost_rag.ports import LLMUnavailableError
from roboost_rag.services.query import (
    NO_INFORMATION,
    QueryService,
    ServiceUnavailableError,
)
from roboost_rag.services.retrieval import RetrievalConfig, RetrievalService
from tests.fakes import FakeEmbedder, FakeLLM, FakeStore
from tests.test_retrieval import indexed_store


class FakeOllamaClient:
    def __init__(self, reply="Hola [1]", models=("qwen3.5:9b",), down=False):
        self.reply, self.models, self.down, self.calls = reply, models, down, []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.down:
            raise ConnectionError("refused")
        return SimpleNamespace(message=SimpleNamespace(content=self.reply))

    def list(self):
        if self.down:
            raise ConnectionError("refused")
        return SimpleNamespace(models=[SimpleNamespace(model=m) for m in self.models])


# --- Ollama adapter --------------------------------------------------------

def test_ollama_uses_configured_model_without_thinking():
    client = FakeOllamaClient(reply="<think>razonando</think>\nRespuesta [1]")
    llm = OllamaLLM("http://h:11434", "qwen3.5:9b", temperature=0.1, client=client)
    assert llm.generate("sys", "prompt") == "Respuesta [1]"
    call = client.calls[0]
    assert call["model"] == "qwen3.5:9b"
    assert call["think"] is False
    assert call["options"] == {"temperature": 0.1}
    assert call["messages"][0] == {"role": "system", "content": "sys"}


def test_ollama_down_raises_unavailable():
    llm = OllamaLLM("http://h:11434", client=FakeOllamaClient(down=True))
    with pytest.raises(LLMUnavailableError):
        llm.generate("sys", "prompt")


def test_check_model_ready():
    assert OllamaLLM("http://h", "qwen3.5:9b", client=FakeOllamaClient()).check_model() is None


def test_check_model_missing_suggests_pull():
    llm = OllamaLLM("http://h", "qwen3.5:9b", client=FakeOllamaClient(models=("bge-m3:latest",)))
    assert "ollama pull qwen3.5:9b" in llm.check_model()


def test_check_model_ollama_down():
    llm = OllamaLLM("http://h:11434", client=FakeOllamaClient(down=True))
    assert "no es accesible en http://h:11434" in llm.check_model()


# --- QueryService ----------------------------------------------------------

def query_service(llm, **cfg):
    store, embedder = indexed_store()
    retrieval = RetrievalService(embedder, store, store, None, RetrievalConfig(**cfg))
    return QueryService(retrieval, llm)


def test_empty_retrieval_does_not_call_llm():
    llm = FakeLLM()
    retrieval = RetrievalService(FakeEmbedder(), FakeStore(), FakeStore(), None)
    answer = QueryService(retrieval, llm).ask("vacaciones", Role.PUBLIC)
    assert answer.text == NO_INFORMATION
    assert answer.sources == []
    assert llm.calls == []


def test_answer_lists_every_source_document():
    llm = FakeLLM(reply="Tienes 23 días [1][2]")
    answer = query_service(llm, final_top_k=2).ask("vacaciones evacuacion", Role.PUBLIC)
    assert answer.text == "Tienes 23 días [1][2]"
    assert {s.path for s in answer.sources} == {"vacaciones.md", "prl.md"}
    system, prompt = llm.calls[0]
    assert "ÚNICAMENTE" in system
    assert "[1]" in prompt and "[2]" in prompt and "Pregunta: vacaciones evacuacion" in prompt


def test_sources_never_include_restricted_documents_for_public():
    answer = query_service(FakeLLM(), final_top_k=10).ask("bandas atlas vacaciones", Role.PUBLIC)
    assert {s.path for s in answer.sources} <= {"vacaciones.md", "prl.md"}


def test_llm_down_gives_safe_message():
    with pytest.raises(ServiceUnavailableError) as exc:
        query_service(FakeLLM(fail=True)).ask("vacaciones", Role.PUBLIC)
    assert "no está disponible" in str(exc.value)
    assert "ollama" not in str(exc.value).lower()
