from citation_agent.document import chunk_document, annotate_document

def test_chunk_document_basic():
    text = "Line one\nLine two\nLine three\nLine four"
    chunks = chunk_document(text, max_lines=2, overlap=1)
    assert len(chunks) >= 2
    assert chunks[0].text.startswith("0001:")

def test_annotate_document_numbers_lines():
    text = "A\nB\nC"
    annotated = annotate_document(text)
    assert "0001:" in annotated
    assert "0003:" in annotated
