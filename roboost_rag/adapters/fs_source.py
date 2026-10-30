"""Reads source documents (.md / .txt with YAML front-matter) from a directory."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

import frontmatter

from roboost_rag.domain import AccessLevel, Document
from roboost_rag.ports import LoadResult

log = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".md", ".txt"}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class FileSystemSource:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def load(self) -> LoadResult:
        # A missing directory (e.g. an unmounted volume) must not look like an empty corpus,
        # or the sync would delete every indexed document.
        if not self.root.is_dir():
            raise FileNotFoundError(f"La carpeta de documentos {self.root} no existe")
        result = LoadResult()
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            rel = path.relative_to(self.root).as_posix()
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                log.warning("Ignorando %s: extensión no soportada", rel)
                continue
            try:
                result.documents.append(self._read(path, rel))
            except Exception as exc:  # unreadable file or malformed front-matter
                log.error("No se pudo leer %s: %s", rel, exc)
                result.failed.append(rel)
        return result

    def _read(self, path: Path, rel: str) -> Document:
        post = frontmatter.loads(path.read_text(encoding="utf-8"))
        meta = dict(post.metadata)

        raw_level = meta.get("access_level")
        level = AccessLevel.from_label(raw_level) if isinstance(raw_level, str) else None
        if level is None:
            log.warning(
                "%s: access_level %r ausente o no válido; se aplica 'admin'", rel, raw_level
            )
            level = AccessLevel.ADMIN

        title = str(meta.get("title") or path.stem.replace("_", " "))
        body = normalize(post.content)
        meta_key = json.dumps(
            {**meta, "title": title, "access_level": level.label}, sort_keys=True, default=str
        )
        return Document(
            path=rel,
            title=title,
            access_level=level,
            body=post.content.strip(),
            content_hash=_sha256(meta_key + "\n" + body),
            body_hash=_sha256(body),
        )
