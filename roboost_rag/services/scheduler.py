"""Runs index synchronisation passes periodically, one at a time."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from roboost_rag.ports import VectorStore
from roboost_rag.services.ingestion import IngestionService, SyncReport

log = logging.getLogger(__name__)


class SyncScheduler:
    def __init__(
        self,
        ingestion: IngestionService,
        store: VectorStore,
        interval_seconds: float,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.ingestion = ingestion
        self.store = store
        self.interval = interval_seconds
        self.sleep = sleep
        self.clock = clock

    def run_once(self) -> SyncReport | None:
        """One pass, or None if another pass holds the lock."""
        with self.store.sync_lock() as acquired:
            if not acquired:
                log.info("Pasada omitida: otra sincronización está en curso")
                return None
            return self.ingestion.sync()

    def run_forever(self, max_passes: int | None = None) -> None:
        """First pass immediately, then one every `interval` seconds. Never dies on errors."""
        passes = 0
        while max_passes is None or passes < max_passes:
            started = self.clock()
            try:
                self.run_once()
            except Exception:  # e.g. database temporarily down
                log.exception("La pasada de sincronización falló; se reintentará")
            passes += 1
            if max_passes is None or passes < max_passes:
                self.sleep(max(0.0, self.interval - (self.clock() - started)))
