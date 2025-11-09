from agents import RunContextWrapper

from citation_agent.document import DocumentChunk
from citation_agent.tools import (
    BriefContext,
    list_brief_sections_impl,
    search_brief_sections_impl,
)


def test_list_sections_returns_preview():
    chunks = [DocumentChunk(index=0, start_line=1, end_line=3, text="0001: Hello world")]
    ctx = RunContextWrapper(context=BriefContext(document_name="x", chunks=chunks))
    result = list_brief_sections_impl(ctx)
    assert "Section 0" in result


def test_search_sections_finds_keyword():
    chunks = [
        DocumentChunk(index=0, start_line=1, end_line=2, text="Case Brown v. Board"),
        DocumentChunk(index=1, start_line=3, end_line=4, text="Random text"),
    ]
    ctx = RunContextWrapper(context=BriefContext(document_name="x", chunks=chunks))
    res = search_brief_sections_impl(ctx, query="Brown")
    assert "Section 0" in res
