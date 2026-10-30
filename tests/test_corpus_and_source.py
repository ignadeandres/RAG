import logging
from collections import Counter
from pathlib import Path

import pytest

from roboost_rag.adapters.fs_source import FileSystemSource
from roboost_rag.domain import AccessLevel
from roboost_rag.services.chunking import Chunker

DOCS = Path(__file__).resolve().parents[1] / "docs"


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_corpus_covers_every_level():
    result = FileSystemSource(DOCS).load()
    assert result.failed == []
    assert len(result.documents) >= 30
    counts = Counter(d.access_level for d in result.documents)
    assert all(counts[level] >= 6 for level in AccessLevel)


def test_corpus_has_multi_chunk_documents():
    chunker = Chunker(3200)  # default CHUNK_SIZE
    docs = FileSystemSource(DOCS).load().documents
    assert sum(len(chunker.split(d)) > 1 for d in docs) >= 4


def test_corpus_has_cross_sensitivity_on_salary_policy():
    docs = FileSystemSource(DOCS).load().documents
    salary_levels = {d.access_level for d in docs if "salarial" in d.title.lower()}
    assert AccessLevel.PUBLIC in salary_levels
    assert salary_levels & {AccessLevel.HR_MANAGER, AccessLevel.ADMIN}


def test_reads_front_matter_recursively(tmp_path):
    write(tmp_path, "beneficios/seguro.md", "---\ntitle: Seguro\naccess_level: public\n---\nTexto")
    [doc] = FileSystemSource(tmp_path).load().documents
    assert doc.path == "beneficios/seguro.md"
    assert doc.title == "Seguro"
    assert doc.access_level is AccessLevel.PUBLIC
    assert doc.body == "Texto"


def test_missing_or_unknown_level_defaults_to_admin(tmp_path, caplog):
    write(tmp_path, "a.md", "---\ntitle: A\n---\nTexto")
    write(tmp_path, "b.txt", "---\ntitle: B\naccess_level: interno\n---\nTexto")
    with caplog.at_level(logging.WARNING):
        docs = FileSystemSource(tmp_path).load().documents
    assert {d.access_level for d in docs} == {AccessLevel.ADMIN}
    assert caplog.text.count("se aplica 'admin'") == 2


def test_unsupported_extension_is_ignored(tmp_path, caplog):
    write(tmp_path, "nomina.xlsx", "binary")
    write(tmp_path, "ok.md", "---\ntitle: OK\naccess_level: public\n---\nTexto")
    with caplog.at_level(logging.WARNING):
        result = FileSystemSource(tmp_path).load()
    assert [d.path for d in result.documents] == ["ok.md"]
    assert result.failed == []
    assert "nomina.xlsx" in caplog.text


def test_unreadable_file_is_reported_as_failed(tmp_path):
    (tmp_path / "roto.md").write_bytes(b"\xff\xfe\x00 not utf8")
    write(tmp_path, "ok.md", "---\ntitle: OK\naccess_level: public\n---\nTexto")
    result = FileSystemSource(tmp_path).load()
    assert result.failed == ["roto.md"]
    assert len(result.documents) == 1


def test_missing_root_raises_instead_of_returning_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        FileSystemSource(tmp_path / "no_montada").load()


def test_hashes_track_level_changes_but_body_hash_does_not(tmp_path):
    write(tmp_path, "d.md", "---\ntitle: D\naccess_level: public\n---\nMismo   texto")
    before = FileSystemSource(tmp_path).load().documents[0]
    write(tmp_path, "d.md", "---\ntitle: D\naccess_level: admin\n---\nMismo texto")
    after = FileSystemSource(tmp_path).load().documents[0]
    assert before.content_hash != after.content_hash
    assert before.body_hash == after.body_hash
