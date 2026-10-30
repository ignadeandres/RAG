from roboost_rag.domain import AccessLevel, Document
from roboost_rag.services.chunking import Chunker, split_text

TEXT = "".join(
    f"Frase {i} sobre el seguro médico y los beneficios de la plantilla."
    + ("\n\n" if i % 4 == 3 else " ")
    for i in range(300)
)


def doc(body: str) -> Document:
    return Document(
        path="d.md", title="Título", access_level=AccessLevel.PUBLIC,
        body=body, content_hash="h", body_hash="b",
    )


def spans(text: str, pieces: list[str]) -> list[tuple[int, int]]:
    """(start, end) of each piece in `text`; TEXT has no repeated sentences."""
    out, cursor = [], 0
    for piece in pieces:
        start = text.index(piece, cursor)
        out.append((start, start + len(piece)))
        cursor = start + 1
    return out


def test_long_text_overlaps_about_ten_percent():
    size = 500
    pieces = split_text(TEXT, size)
    assert len(pieces) > 5
    assert all(len(p) <= size for p in pieces)
    for (_, prev_end), (start, _) in zip(spans(TEXT, pieces), spans(TEXT, pieces)[1:]):
        assert 0.05 * size <= prev_end - start <= 0.1 * size


def test_whole_text_is_covered():
    text = TEXT.strip()
    s = spans(text, split_text(text, 500))
    assert s[0][0] == 0 and s[-1][1] == len(text)
    assert all(start <= prev_end for (_, prev_end), (start, _) in zip(s, s[1:]))


def test_text_without_separators_is_hard_cut():
    pieces = split_text("x" * 2500, 1000)
    assert all(len(p) <= 1000 for p in pieces)
    assert len(pieces) == 3


def test_short_document_single_chunk():
    chunks = Chunker(size=3200).split(doc("Texto corto."))
    assert len(chunks) == 1
    assert chunks[0].content == "Título\n\nTexto corto."


def test_chunks_carry_title_and_respect_size():
    size = 400
    chunks = Chunker(size=size).split(doc(TEXT))
    assert [c.position for c in chunks] == list(range(len(chunks)))
    assert all(c.content.startswith("Título\n\n") for c in chunks)
    assert all(len(c.content) <= size for c in chunks)
