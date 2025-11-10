import pytest

from citation_agent.document import chunk_document, annotate_document

def test_chunk_document_basic():
    text = "Line one\nLine two\nLine three\nLine four"
    chunks = chunk_document(text, max_lines=2, overlap=1)
    assert len(chunks) >= 2
    assert chunks[0].text.startswith("0001:")


def test_chunk_document_allows_zero_overlap():
    text = "Line one\nLine two\nLine three"
    chunks = chunk_document(text, max_lines=2, overlap=0)
    assert len(chunks) == 2
    assert chunks[1].start_line == 3


@pytest.mark.parametrize(
    "max_lines, overlap, message",
    [
        (0, 0, "max_lines must be a positive integer"),
        (-1, 0, "max_lines must be a positive integer"),
        (2, -1, "overlap cannot be negative"),
        (4, 4, "overlap must be smaller than max_lines"),
        (5, 6, "overlap must be smaller than max_lines"),
    ],
)
def test_chunk_document_invalid_parameters(max_lines, overlap, message):
    text = "Line one\nLine two"
    with pytest.raises(ValueError) as exc_info:
        chunk_document(text, max_lines=max_lines, overlap=overlap)
    assert message in str(exc_info.value)

def test_annotate_document_numbers_lines():
    text = "A\nB\nC"
    annotated = annotate_document(text)
    assert "0001:" in annotated
    assert "0003:" in annotated
