"""Domain model: access levels, roles, documents, chunks and answers."""

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict


class AccessLevel(IntEnum):
    """Sensitivity of a document. Higher value = more restricted."""

    PUBLIC = 0
    HR_MANAGER = 1
    ADMIN = 2

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def from_label(cls, label: str) -> AccessLevel | None:
        try:
            return cls[label.strip().upper()]
        except (KeyError, AttributeError):
            return None


class Role(StrEnum):
    PUBLIC = "public"
    HR_MANAGER = "hr_manager"
    ADMIN = "admin"

    @property
    def clearance(self) -> AccessLevel:
        """Highest access level this role may read."""
        return AccessLevel[self.name]


def visible_levels(role: Role) -> list[AccessLevel]:
    """Single source of truth for the role hierarchy public ⊂ hr_manager ⊂ admin."""
    return [level for level in AccessLevel if level <= role.clearance]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Document(_Frozen):
    """A source document read from docs/."""

    path: str
    title: str
    access_level: AccessLevel
    body: str
    content_hash: str  # changes when body, title or access level change
    body_hash: str  # identical bodies share it (deduplication)


class Chunk(_Frozen):
    position: int
    content: str


class RetrievedChunk(_Frozen):
    chunk_id: int
    document_path: str
    title: str
    content: str
    access_level: AccessLevel
    score: float


class Source(_Frozen):
    title: str
    path: str
    access_level: AccessLevel


class Answer(_Frozen):
    text: str
    sources: list[Source] = []
