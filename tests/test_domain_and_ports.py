import pytest

from roboost_rag.config import ConfigError, load_settings
from roboost_rag.domain import AccessLevel, Role, visible_levels
from roboost_rag.ports import (
    LLM,
    DocumentSource,
    Embedder,
    LexicalIndex,
    Reranker,
    VectorStore,
)
from tests.fakes import FakeEmbedder, FakeLLM, FakeReranker, FakeSource, FakeStore


def test_role_hierarchy():
    assert visible_levels(Role.PUBLIC) == [AccessLevel.PUBLIC]
    assert visible_levels(Role.HR_MANAGER) == [AccessLevel.PUBLIC, AccessLevel.HR_MANAGER]
    assert visible_levels(Role.ADMIN) == list(AccessLevel)


def test_access_level_labels():
    assert AccessLevel.from_label("hr_manager") is AccessLevel.HR_MANAGER
    assert AccessLevel.from_label(" ADMIN ") is AccessLevel.ADMIN
    assert AccessLevel.from_label("interno") is None
    assert AccessLevel.HR_MANAGER.label == "hr_manager"


def test_fakes_satisfy_ports():
    store = FakeStore()
    assert isinstance(FakeSource(), DocumentSource)
    assert isinstance(FakeEmbedder(), Embedder)
    assert isinstance(store, VectorStore)
    assert isinstance(store, LexicalIndex)
    assert isinstance(FakeReranker(), Reranker)
    assert isinstance(FakeLLM(), LLM)


def test_openai_provider_without_key_gives_clear_error(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_settings()


def test_defaults_need_no_external_keys(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for var in ("OPENAI_API_KEY", "COHERE_API_KEY", "EMBEDDING_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REINDEX_INTERVAL_SECONDS", "60")
    settings = load_settings()
    assert settings.embedding_provider == "ollama"
    assert settings.embedding_model == "bge-m3"
    assert settings.embedding_dimensions == 1024
    assert settings.reindex_interval_seconds == 60
    assert settings.cohere_api_key is None
