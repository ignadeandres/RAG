"""Splits documents into chunks of at most `size` characters with a 10% overlap."""

from __future__ import annotations

from roboost_rag.domain import Chunk, Document

# Preferred cut points, best first.
SEPARATORS = ("\n\n", "\n", ". ", " ")
OVERLAP_RATIO = 0.10


def _cut_point(text: str, start: int, end: int) -> int:
    """Last separator boundary in the second half of text[start:end], else `end`."""
    floor = start + (end - start) // 2
    for sep in SEPARATORS:
        pos = text.rfind(sep, floor, end)
        if pos != -1:
            return pos + len(sep)
    return end


def _overlap_start(text: str, end: int, overlap: int) -> int:
    """Start of the overlap window before `end`, moved forward to a word boundary."""
    start = max(end - overlap, 0)
    if start > 0 and not text[start - 1].isspace():
        space = text.find(" ", start, end)
        if space != -1:
            start = space + 1
    return start


def split_text(text: str, size: int) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    overlap = int(size * OVERLAP_RATIO)
    pieces: list[str] = []
    start = 0
    while True:
        end = min(start + size, len(text))
        if end < len(text):
            end = _cut_point(text, start, end)
        pieces.append(text[start:end])
        if end >= len(text):
            return pieces
        start = max(_overlap_start(text, end, overlap), start + 1)


class Chunker:
    def __init__(self, size: int):
        self.size = size

    def split(self, document: Document) -> list[Chunk]:
        """Each chunk is prefixed with the document title; the prefix counts towards `size`."""
        prefix = f"{document.title}\n\n"
        budget = max(self.size - len(prefix), 1)
        return [
            Chunk(position=i, content=prefix + piece)
            for i, piece in enumerate(split_text(document.body, budget))
        ]
