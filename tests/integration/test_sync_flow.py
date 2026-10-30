"""End-to-end sync against ParadeDB: add, access-level change and deletion of a document."""

import os

import pytest

from roboost_rag.adapters.fs_source import FileSystemSource
from roboost_rag.adapters.paradedb_store import ParadeDBStore
from roboost_rag.domain import Role
from roboost_rag.services.chunking import Chunker
from roboost_rag.services.ingestion import IngestionService
from roboost_rag.services.retrieval import RetrievalConfig, RetrievalService
from roboost_rag.services.scheduler import SyncScheduler
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.integration


class PaddedEmbedder(FakeEmbedder):
    """FakeEmbedder padded to the 1024 dimensions of the schema."""

    def embed(self, texts):
        return [v + [0.0] * (1024 - len(v)) for v in super().embed(texts)]


@pytest.fixture
def env(tmp_path):
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL not set (tests TRUNCATE tables: never point it at the live DB)")
    store = ParadeDBStore(dsn)
    with store.pool.connection() as conn:
        conn.execute("TRUNCATE documents CASCADE")
    embedder = PaddedEmbedder()
    ingestion = IngestionService(FileSystemSource(tmp_path), Chunker(3200), embedder, store)
    scheduler = SyncScheduler(ingestion, store, 300)
    retrieval = RetrievalService(embedder, store, store, None, RetrievalConfig(final_top_k=5))
    yield tmp_path, scheduler, retrieval
    with store.pool.connection() as conn:
        conn.execute("TRUNCATE documents CASCADE")
    store.close()


def write(root, level):
    (root / "nuevo.md").write_text(
        f"---\ntitle: Política de mascotas\naccess_level: {level}\n---\n"
        "Se permite traer perros a la oficina los viernes.",
        encoding="utf-8",
    )


def paths(retrieval, role):
    return {c.document_path for c in retrieval.retrieve("perros oficina viernes", role)}


def test_add_change_level_and_delete(env):
    root, scheduler, retrieval = env

    write(root, "public")
    assert scheduler.run_once().added == ["nuevo.md"]
    assert paths(retrieval, Role.PUBLIC) == {"nuevo.md"}

    write(root, "admin")
    assert scheduler.run_once().updated == ["nuevo.md"]
    assert paths(retrieval, Role.PUBLIC) == set()
    assert paths(retrieval, Role.HR_MANAGER) == set()
    assert paths(retrieval, Role.ADMIN) == {"nuevo.md"}

    (root / "nuevo.md").unlink()
    assert scheduler.run_once().removed == ["nuevo.md"]
    assert paths(retrieval, Role.ADMIN) == set()
