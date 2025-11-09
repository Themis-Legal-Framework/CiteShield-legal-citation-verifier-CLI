"""Custom function tools exposed to the legal citation agent.

This module defines the custom tools that allow the OpenAI agent to interact
with legal documents during citation verification. These tools enable:
    - Browsing document sections with pagination
    - Retrieving specific sections by index
    - Searching for keywords across the document

The tools are designed to minimize token usage by providing only the relevant
portions of the document to the agent when needed, rather than processing the
entire document at once.

All tools operate on a BriefContext that maintains the document state during
agent execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents import RunContextWrapper, function_tool

from .document import DocumentChunk


@dataclass
class BriefContext:
    """Context object holding document data for agent tool access.

    This context is passed to all custom tools, allowing them to access
    the chunked document and metadata. It persists throughout the agent's
    execution.

    Attributes:
        document_name: Name of the file being analyzed
        chunks: List of DocumentChunk objects containing the full document
        overview: Precomputed summary of document structure
    """

    document_name: str
    chunks: list[DocumentChunk] = field(default_factory=list)
    overview: str = ""

    def get_chunk(self, section_index: int) -> DocumentChunk:
        """Retrieve a specific chunk by index.

        Args:
            section_index: Zero-based index of the chunk to retrieve

        Returns:
            The requested DocumentChunk

        Raises:
            ValueError: If the section_index is out of range
        """
        if section_index < 0 or section_index >= len(self.chunks):
            raise ValueError(
                f"Section index {section_index} is invalid. Valid range: 0-{len(self.chunks) - 1}"
            )
        return self.chunks[section_index]


def _score_chunk(chunk: DocumentChunk, query: str) -> float:
    """Score a chunk's relevance to a search query.

    Uses a simple ranking function based on:
        - Keyword frequency in the chunk
        - Number of unique keywords found (coverage)
        - Keyword density relative to chunk length

    Args:
        chunk: The DocumentChunk to score
        query: Search query string

    Returns:
        A numeric relevance score (higher is more relevant)

    Note:
        This is a lightweight scoring function. For production use with large
        documents, consider integrating a vector store or BM25 ranking.
    """

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
    """List document sections with pagination support.

    This tool allows the agent to browse through the document structure without
    loading full section contents. It's useful for getting oriented in the document
    and deciding which sections to examine in detail.

    Args:
        ctx: Runtime context wrapper containing the BriefContext
        start_section: Index of the first section to list (default: 0)
        limit: Maximum number of sections to return (default: 5)

    Returns:
        A formatted string listing each section with its index, line range,
        and a brief preview of the content

    Example:
        >>> list_brief_sections_impl(ctx, start_section=0, limit=2)
        'Section 0 (lines 1-40): In support of our motion...\\nSection 1 (lines 36-76): Further...'
    """

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
    """Retrieve the full text of a specific document section.

    This tool provides the complete content of a section with line numbers,
    allowing the agent to examine citations in detail and reference specific
    lines in its analysis.

    Args:
        ctx: Runtime context wrapper containing the BriefContext
        section_index: Zero-based index of the section to retrieve

    Returns:
        The complete section text with line numbers in the format:
        "Section N (lines X-Y):\\nNNNN: content..."

    Raises:
        ValueError: If the section_index is out of bounds

    Example:
        >>> get_brief_section_impl(ctx, section_index=0)
        'Section 0 (lines 1-40):\\n0001: In support of our motion...'
    """

    chunk = ctx.context.get_chunk(section_index)
    return f"Section {chunk.index} (lines {chunk.start_line}-{chunk.end_line}):\n{chunk.text}"


def search_brief_sections_impl(
    ctx: RunContextWrapper[BriefContext],
    query: str,
    limit: int = 3,
) -> str:
    """Search for sections relevant to a keyword query.

    This tool enables the agent to find sections containing specific citations,
    case names, or legal concepts without reading the entire document. It uses
    a simple keyword-based ranking to return the most relevant sections.

    Args:
        ctx: Runtime context wrapper containing the BriefContext
        query: Search terms (e.g., case name, statute number, legal concept)
        limit: Maximum number of results to return (default: 3)

    Returns:
        A formatted string listing the most relevant sections with their
        previews, or a message if no matches were found

    Example:
        >>> search_brief_sections_impl(ctx, query="Brown v. Board", limit=2)
        'Section 0 (lines 1-40): In support of our motion...\\nSection 5 (lines 180-220): As established...'

    Note:
        The search uses simple keyword matching. For better recall with legal
        citations, the agent should try variations (abbreviated names, reporter
        citations, etc.).
    """

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


# Export tools wrapped with function_tool decorator for OpenAI agent integration
list_brief_sections = function_tool(list_brief_sections_impl)
"""Agent tool: Browse document sections with pagination."""

get_brief_section = function_tool(get_brief_section_impl)
"""Agent tool: Retrieve full text of a specific section."""

search_brief_sections = function_tool(search_brief_sections_impl)
"""Agent tool: Search for sections by keyword query."""
