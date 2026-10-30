from roboost_rag.domain import AccessLevel, Document
from roboost_rag.services.chunking import Chunker
from roboost_rag.services.ingestion import IngestionService
from tests.fakes import FakeEmbedder, FakeSource, FakeStore


def doc(path, body="texto", level=AccessLevel.PUBLIC, version="1"):
    return Document(
        path=path, title=path, access_level=level, body=body,
        content_hash=f"{path}:{body}:{level}:{version}", body_hash=f"body:{body}",
    )


def service(documents, failed=None, embedder=None, store=None):
    source = FakeSource(documents, failed)
    store = store or FakeStore()
    embedder = embedder or FakeEmbedder()
    return IngestionService(source, Chunker(3200), embedder, store), source, embedder, store


def test_first_pass_adds_everything():
    svc, *_ = service([doc("a.md", "uno"), doc("b.md", "dos")])
    report = svc.sync()
    assert report.added == ["a.md", "b.md"]


def test_second_pass_without_changes_does_not_call_embedder():
    svc, _, embedder, _ = service([doc("a.md", "uno"), doc("b.md", "dos")])
    svc.sync()
    calls = len(embedder.calls)
    report = svc.sync()
    assert len(embedder.calls) == calls
    assert report.skipped == ["a.md", "b.md"]
    assert report.added == report.updated == []


def test_modified_document_is_reindexed():
    svc, source, _, store = service([doc("a.md", "uno")])
    svc.sync()
    source.documents = [doc("a.md", "uno", level=AccessLevel.ADMIN, version="2")]
    report = svc.sync()
    assert report.updated == ["a.md"]
    assert store.documents["a.md"].access_level is AccessLevel.ADMIN


def test_deleted_document_is_removed():
    svc, source, _, store = service([doc("a.md", "uno"), doc("b.md", "dos")])
    svc.sync()
    source.documents = [doc("a.md", "uno")]
    report = svc.sync()
    assert report.removed == ["b.md"]
    assert "b.md" not in store.indexed_hashes()


def test_unreadable_file_is_not_removed_from_index():
    svc, source, _, store = service([doc("a.md", "uno")])
    svc.sync()
    source.documents, source.failed = [], ["a.md"]
    report = svc.sync()
    assert report.removed == []
    assert report.failed == ["a.md"]
    assert "a.md" in store.indexed_hashes()


def test_duplicate_content_indexed_once_with_most_restrictive_level():
    svc, _, embedder, store = service([
        doc("public_copy.md", "igual", AccessLevel.PUBLIC),
        doc("hr_copy.md", "igual", AccessLevel.HR_MANAGER),
    ])
    report = svc.sync()
    assert report.added == ["hr_copy.md"]
    assert report.skipped == ["public_copy.md"]
    assert list(store.documents) == ["hr_copy.md"]
    assert len(embedder.calls) == 1


def test_embedding_failure_keeps_previous_version_and_continues():
    store = FakeStore()
    svc, source, _, _ = service([doc("a.md", "uno"), doc("b.md", "dos")], store=store)
    svc.sync()
    before = [r for r, _ in store.rows if r.document_path == "a.md"]

    source.documents = [doc("a.md", "ROMPE", version="2"), doc("b.md", "dos v2", version="2")]
    svc.embedder = FakeEmbedder(fail_on="ROMPE")
    report = svc.sync()

    assert report.failed == ["a.md"]
    assert report.updated == ["b.md"]
    assert [r for r, _ in store.rows if r.document_path == "a.md"] == before
    assert store.documents["a.md"].body == "uno"
