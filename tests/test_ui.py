"""Streamlit AppTest of the chat UI with fake services (no DB, OpenAI or Ollama)."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from roboost_rag import container as di
from roboost_rag.services.auth import UserDirectory, hash_password
from roboost_rag.services.query import QueryService
from roboost_rag.services.retrieval import RetrievalConfig, RetrievalService
from tests.fakes import FakeLLM
from tests.test_retrieval import indexed_store

APP = str(Path(__file__).resolve().parents[1] / "ui" / "app.py")


@pytest.fixture(scope="module")
def users():
    return UserDirectory(f"ana:{hash_password('pw')}:public,luis:{hash_password('pw')}:hr_manager")


@pytest.fixture
def app(monkeypatch, users):
    store, embedder = indexed_store()
    retrieval = RetrievalService(embedder, store, store, None, RetrievalConfig(final_top_k=2))
    llm = FakeLLM(reply="Tienes 23 días [1]")
    fake = SimpleNamespace(
        users=users,
        query=QueryService(retrieval, llm),
        startup_warnings=lambda: [],
        llm=llm,
    )
    monkeypatch.setattr(di, "build", lambda: fake)
    st.cache_resource.clear()  # the app caches the container across runs
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    at.fake = fake
    return at


def login(at, user="ana", password="pw"):
    at.text_input[0].input(user)
    at.text_input[1].input(password)
    at.button[0].click()
    at.run()


def test_without_session_only_login_form(app):
    assert len(app.text_input) == 2
    assert len(app.chat_input) == 0


def test_invalid_credentials_rejected(app):
    login(app, password="wrong")
    assert "incorrectos" in app.error[0].value
    assert len(app.chat_input) == 0


def test_login_shows_role_and_chat(app):
    login(app, user="luis")
    assert any("hr_manager" in m.value for m in app.sidebar.markdown)
    assert len(app.chat_input) == 1


def test_question_shows_answer_and_sources(app):
    login(app)
    app.chat_input[0].set_value("vacaciones").run()
    assert any("23 días" in m.value for m in app.markdown)
    assert any("vacaciones.md" in c.value for c in app.caption)


def test_logout_clears_history(app):
    login(app)
    app.chat_input[0].set_value("vacaciones").run()
    app.sidebar.button[0].click().run()
    assert len(app.chat_input) == 0
    assert not any("23 días" in m.value for m in app.markdown)
    assert "history" not in app.session_state


def test_backend_down_shows_safe_error(app):
    login(app)
    app.fake.llm.fail = True
    app.chat_input[0].set_value("vacaciones").run()
    assert "no está disponible" in app.error[0].value
    assert not app.exception
