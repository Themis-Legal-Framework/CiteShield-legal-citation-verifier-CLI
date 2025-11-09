"""Custom function tools exposed to the legal citation agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from agents import RunContextWrapper, function_tool

from .document import DocumentChunk


@dataclass
class BriefContext:
    """Holds the uploaded brief so that tools can retrieve pieces on demand."""

    document_name: str
    chunks: list[DocumentChunk] = field(default_factory=list)
    overview: str = ""

    def get_chunk(self, section_index: int) -> DocumentChunk:
        if section_index < 0 or section_index >= len(self.chunks):
            raise ValueError(
                f"Section index {section_index} is invalid. Valid range: 0-{len(self.chunks) - 1}"
            )
        return self.chunks[section_index]


def _score_chunk(chunk: DocumentChunk, query: str) -> float:
    """Very small ranking function so the agent can request the most relevant sections."""

    haystack = chunk.text.lower()
    keywords = [token for token in query.lower().split() if len(token) > 2]
    if not keywords:
        return 0.0
    freq = sum(haystack.count(token) for token in keywords)
    coverage = len({token for token in keywords if token in haystack})
    density = freq / max(1, len(haystack.split()))
    return freq + coverage + density


def list_brief_sections_impl(
    ctx: RunContextWrapper[BriefContext],
    start_section: int = 0,
    limit: int = 5,
) -> str:
    """List a few sections from the uploaded brief with their line ranges and previews."""

    context = ctx.context
    end = min(len(context.chunks), start_section + max(1, limit))
    rows = []
    for chunk in context.chunks[start_section:end]:
        rows.append(
            f"Section {chunk.index} (lines {chunk.start_line}-{chunk.end_line}): {chunk.preview}"
        )
    return "\n".join(rows) if rows else "No sections available."


def get_brief_section_impl(
    ctx: RunContextWrapper[BriefContext],
    section_index: int,
) -> str:
    """Return the verbatim text (with line numbers) of a specific section."""

    chunk = ctx.context.get_chunk(section_index)
    return f"Section {chunk.index} (lines {chunk.start_line}-{chunk.end_line}):\n{chunk.text}"


def search_brief_sections_impl(
    ctx: RunContextWrapper[BriefContext],
    query: str,
    limit: int = 3,
) -> str:
    """Return the most relevant sections for a query (case name, issue, or quote)."""

    context = ctx.context
    scored = [(chunk, _score_chunk(chunk, query)) for chunk in context.chunks]
    scored.sort(key=lambda item: item[1], reverse=True)
    top_chunks = [chunk for chunk, score in scored if score > 0][: limit or 3]
    if not top_chunks:
        return "No relevant sections found. Try a different query."
    rows = []
    for chunk in top_chunks:
        rows.append(
            f"Section {chunk.index} (lines {chunk.start_line}-{chunk.end_line}): {chunk.preview}"
        )
    return "\n".join(rows)


list_brief_sections = function_tool(list_brief_sections_impl)
get_brief_section = function_tool(get_brief_section_impl)
search_brief_sections = function_tool(search_brief_sections_impl)
