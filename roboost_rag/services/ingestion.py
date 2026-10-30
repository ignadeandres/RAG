"""Synchronises the index with the document source: add, update, delete, deduplicate."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from roboost_rag.domain import Document
from roboost_rag.ports import DocumentSource, Embedder, VectorStore
from roboost_rag.services.chunking import Chunker

log = logging.getLogger(__name__)


@dataclass
class SyncReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # unchanged or duplicate
    failed: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"añadidos={len(self.added)} actualizados={len(self.updated)} "
            f"eliminados={len(self.removed)} omitidos={len(self.skipped)} "
            f"fallidos={len(self.failed)}"
        )


def deduplicate(documents: list[Document]) -> tuple[list[Document], list[str]]:
    """Keep one document per identical body: the most restrictive, then alphabetical path."""
    groups: dict[str, list[Document]] = {}
    for doc in documents:
        groups.setdefault(doc.body_hash, []).append(doc)
    kept, duplicates = [], []
    for group in groups.values():
        group.sort(key=lambda d: (-d.access_level, d.path))
        kept.append(group[0])
        for dup in group[1:]:
            log.info("Duplicado: %s tiene el mismo contenido que %s", dup.path, group[0].path)
            duplicates.append(dup.path)
    return kept, duplicates


class IngestionService:
    def __init__(
        self, source: DocumentSource, chunker: Chunker, embedder: Embedder, store: VectorStore
    ):
        self.source = source
        self.chunker = chunker
        self.embedder = embedder
        self.store = store

    def sync(self) -> SyncReport:
        loaded = self.source.load()
        report = SyncReport(failed=list(loaded.failed))
        documents, report.skipped = deduplicate(loaded.documents)
        indexed = self.store.indexed_hashes()

        for doc in documents:
            previous = indexed.get(doc.path)
            if previous == doc.content_hash:
                report.skipped.append(doc.path)
                continue
            try:
                self._index(doc)
            except Exception:
                # The previous version (if any) stays in the index untouched.
                log.exception("No se pudo indexar %s", doc.path)
                report.failed.append(doc.path)
                continue
            (report.updated if previous else report.added).append(doc.path)

        # Unreadable files are kept: they may still exist and be fixed later.
        present = {d.path for d in documents} | set(loaded.failed)
        for path in sorted(indexed.keys() - present):
            self.store.delete_document(path)
            report.removed.append(path)

        log.info("Sincronización completada: %s", report.summary())
        return report

    def _index(self, doc: Document) -> None:
        chunks = self.chunker.split(doc)
        # Embeddings are computed before touching the store so a failure leaves it intact.
        embeddings = self.embedder.embed([c.content for c in chunks])
        self.store.replace_document(doc, chunks, embeddings)
