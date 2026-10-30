from roboost_rag.domain import AccessLevel, Document
from roboost_rag.services.chunking import Chunker
from roboost_rag.services.ingestion import IngestionService
from roboost_rag.services.scheduler import SyncScheduler
from tests.fakes import FakeEmbedder, FakeSource, FakeStore


def doc(path):
    return Document(path=path, title=path, access_level=AccessLevel.PUBLIC, body=path,
                    content_hash=path, body_hash=path)


def scheduler(source, store=None, embedder=None, sleeps=None):
    store = store or FakeStore()
    ingestion = IngestionService(source, Chunker(3200), embedder or FakeEmbedder(), store)
    sleeps = sleeps if sleeps is not None else []
    return SyncScheduler(ingestion, store, 300, sleep=sleeps.append, clock=lambda: 0.0), store


def test_concurrent_pass_is_skipped():
    embedder = FakeEmbedder()
    sched, store = scheduler(FakeSource([doc("a.md")]), embedder=embedder)
    store.locked = True  # another pass in progress
    assert sched.run_once() is None
    assert embedder.calls == []


def test_pass_runs_and_releases_lock():
    sched, store = scheduler(FakeSource([doc("a.md")]))
    report = sched.run_once()
    assert report.added == ["a.md"]
    assert store.locked is False


def test_corrupt_document_does_not_stop_the_pass():
    sched, store = scheduler(FakeSource([doc("ok.md")], failed=["roto.md"]))
    report = sched.run_once()
    assert report.added == ["ok.md"]
    assert report.failed == ["roto.md"]


class FlakySource(FakeSource):
    def __init__(self):
        super().__init__([doc("a.md")])
        self.loads = 0

    def load(self):
        self.loads += 1
        if self.loads == 1:
            raise ConnectionError("database down")
        return super().load()


def test_missing_docs_dir_keeps_index_intact(tmp_path):
    from roboost_rag.adapters.fs_source import FileSystemSource

    store = FakeStore()
    scheduler(FakeSource([doc("a.md")]), store=store)[0].run_once()
    unmounted, _ = scheduler(FileSystemSource(tmp_path / "no_montada"), store=store)
    unmounted.run_forever(max_passes=1)  # the failed pass is logged, not fatal
    assert "a.md" in store.indexed_hashes()


def test_loop_survives_failed_pass_and_waits_interval():
    source, sleeps = FlakySource(), []
    sched, store = scheduler(source, sleeps=sleeps)
    sched.run_forever(max_passes=3)
    assert source.loads == 3
    assert sleeps == [300, 300]
    assert "a.md" in store.indexed_hashes()
