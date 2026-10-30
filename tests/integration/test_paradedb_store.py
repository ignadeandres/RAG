"""Integration tests against a real ParadeDB.

Run against a dedicated database (the tests TRUNCATE tables), see README:
    TEST_DATABASE_URL=postgresql://roboost:roboost@localhost:5432/roboost_test pytest -m integration
"""

import os
import random

import pytest

from roboost_rag.adapters.paradedb_store import ParadeDBStore
from roboost_rag.domain import AccessLevel, Chunk, Document, Role

pytestmark = pytest.mark.integration

DIM = 1024


def vec(seed: int) -> list[float]:
    rnd = random.Random(seed)
    return [rnd.uniform(-1, 1) for _ in range(DIM)]


def doc(path: str, level: AccessLevel, title: str = "T") -> Document:
    return Document(
        path=path, title=title, access_level=level, body="", content_hash=path, body_hash=path
    )


@pytest.fixture
def store():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL not set (tests TRUNCATE tables: never point it at the live DB)")
    s = ParadeDBStore(dsn)
    with s.pool.connection() as conn:
        conn.execute("TRUNCATE documents CASCADE")
    yield s
    with s.pool.connection() as conn:
        conn.execute("TRUNCATE documents CASCADE")
    s.close()


def add(store, path, level, texts, seed=0):
    chunks = [Chunk(position=i, content=t) for i, t in enumerate(texts)]
    store.replace_document(doc(path, level), chunks, [vec(seed + i) for i in range(len(texts))])


def test_public_never_receives_restricted_rows(store):
    add(store, "pub.md", AccessLevel.PUBLIC, ["vacaciones anuales"] * 3, seed=1)
    add(store, "hr.md", AccessLevel.HR_MANAGER, ["bandas salariales vacaciones"] * 3, seed=10)
    add(store, "adm.md", AccessLevel.ADMIN, ["expedientes vacaciones"] * 3, seed=20)
    vector_hits = store.search_vector(vec(10), Role.PUBLIC, 20)
    lexical_hits = store.search_lexical("vacaciones", Role.PUBLIC, 20)
    assert vector_hits and lexical_hits
    assert {c.access_level for c in vector_hits + lexical_hits} == {AccessLevel.PUBLIC}


def test_selective_filter_still_returns_limit_rows(store):
    add(store, "adm.md", AccessLevel.ADMIN, [f"admin {i}" for i in range(300)], seed=1000)
    add(store, "pub.md", AccessLevel.PUBLIC, [f"public {i}" for i in range(15)], seed=5000)
    hits = store.search_vector(vec(1000), Role.PUBLIC, 10)  # query close to admin rows
    assert len(hits) == 10
    assert all(c.access_level is AccessLevel.PUBLIC for c in hits)


def test_bm25_finds_exact_term(store):
    add(store, "prl.md", AccessLevel.PUBLIC, ["Procedimiento PRL-04 de evacuación"], seed=1)
    add(store, "otro.md", AccessLevel.PUBLIC, ["Política de teletrabajo"], seed=2)
    hits = store.search_lexical("PRL-04", Role.PUBLIC, 5)
    assert hits[0].document_path == "prl.md"


def test_bm25_spanish_stemming_and_accents(store):
    add(store, "v.md", AccessLevel.PUBLIC, ["Días de vacaciones y evacuación"], seed=1)
    assert store.search_lexical("vacacion", Role.PUBLIC, 5)
    assert store.search_lexical("evacuacion", Role.PUBLIC, 5)


def test_bm25_admin_term_invisible_for_public(store):
    add(store, "atlas.md", AccessLevel.ADMIN, ["Proyecto Atlas reestructuración"], seed=1)
    assert store.search_lexical("Atlas", Role.PUBLIC, 5) == []
    assert store.search_lexical("Atlas", Role.HR_MANAGER, 5) == []
    assert store.search_lexical("Atlas", Role.ADMIN, 5)


@pytest.mark.parametrize("q", ['"', "AND OR NOT", "title:(", "*?~^", "   ", "PRL-04)"])
def test_bm25_special_characters_do_not_fail(store, q):
    add(store, "prl.md", AccessLevel.PUBLIC, ["Procedimiento PRL-04"], seed=1)
    store.search_lexical(q, Role.PUBLIC, 5)


def test_replace_is_atomic_and_updates_level(store):
    add(store, "d.md", AccessLevel.PUBLIC, ["uno", "dos", "tres"], seed=1)
    add(store, "d.md", AccessLevel.ADMIN, ["nuevo"], seed=1)
    assert store.search_vector(vec(1), Role.PUBLIC, 10) == []
    hits = store.search_vector(vec(1), Role.ADMIN, 10)
    assert [c.content for c in hits] == ["nuevo"]


def test_delete_and_hashes(store):
    add(store, "d.md", AccessLevel.PUBLIC, ["uno"], seed=1)
    assert store.indexed_hashes() == {"d.md": "d.md"}
    store.delete_document("d.md")
    assert store.indexed_hashes() == {}
    assert store.search_vector(vec(1), Role.ADMIN, 10) == []


def test_sync_lock_is_exclusive(store):
    with store.sync_lock() as first:
        with store.sync_lock() as second:
            assert first is True
            assert second is False
