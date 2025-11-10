"""Utilities for loading and chunking uploaded briefs.

This module handles document ingestion and preprocessing for the citation agent.
It supports multiple file formats (text, PDF, Word) and provides utilities to:
    - Load documents from various file formats
    - Split documents into manageable chunks for agent processing
    - Add line numbers for precise citation reference
    - Generate previews of document sections

The chunking strategy uses overlapping windows to ensure citations near chunk
boundaries are not missed during analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class DocumentChunk:
    """Represents a contiguous block of the source document with original line numbers.

    Chunks are used to break large documents into manageable pieces that can be
    efficiently processed by the agent. Each chunk maintains references to the
    original line numbers so that findings can be traced back to the source.

    Attributes:
        index: Sequential chunk number (0-indexed)
        start_line: First line number in this chunk (1-indexed)
        end_line: Last line number in this chunk (1-indexed, inclusive)
        text: The actual content with line numbers prefixed (format: "NNNN: content")
    """

    index: int
    start_line: int
    end_line: int
    text: str

    @property
    def preview(self) -> str:
        """Generate a short preview of this chunk's content.

        Returns:
            A truncated string showing the first few lines of the chunk,
            limited to 160 characters with ellipsis if longer.
        """
        snippet = self.text.splitlines()
        joined = " ".join(line.split(":", 1)[-1].strip() for line in snippet[:3])
        return (joined[:160] + "...") if len(joined) > 160 else joined


def load_document_text(path: Path) -> str:
    """Load and extract text from a document file.

    Supports multiple file formats:
        - Plain text (.txt, .md, or no extension)
        - PDF files (.pdf) - requires pypdf library
        - Microsoft Word (.docx) - requires python-docx library

    Args:
        path: Path to the document file to load

    Returns:
        The complete document text as a unicode string

    Raises:
        FileNotFoundError: If the file doesn't exist
        RuntimeError: If required libraries for PDF/Word are not installed
        ValueError: If the file extension is not supported

    Note:
        For PDF and Word files, the respective optional dependencies must be
        installed: `pip install citation-agent[pdf]` or `pip install citation-agent[docx]`
    """

    if not path.exists():
        raise FileNotFoundError(f"No file found at {path}")

    suffix = path.suffix.lower()
    if suffix in {"", ".txt", ".md"}:
        return path.read_text(encoding="utf-8")

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Reading PDF files requires the optional 'pdf' extra: pip install citation-agent[pdf]"
            ) from exc

        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)

    if suffix == ".docx":
        try:
            import docx  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Reading Word files requires the optional 'docx' extra: pip install citation-agent[docx]"
            ) from exc

        document = docx.Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    raise ValueError(f"Unsupported file extension '{suffix}'. Convert the brief to text first.")


def chunk_document(
    text: str,
    *,
    max_lines: int = 40,
    overlap: int = 5,
) -> list[DocumentChunk]:
    """Split text into overlapping windows while preserving original line numbers.

    This function divides a document into manageable chunks for agent processing.
    Each chunk overlaps with the next to ensure citations spanning chunk boundaries
    are not missed. Line numbers from the original document are preserved and
    prefixed to each line in the format "NNNN: content".

    Args:
        text: The complete document text to chunk
        max_lines: Maximum number of lines per chunk (default: 40)
        overlap: Number of lines to overlap between consecutive chunks (default: 5)

    Raises:
        ValueError: If ``max_lines`` is not positive, ``overlap`` is negative, or
            ``overlap`` is greater than or equal to ``max_lines``.

    Returns:
        A list of DocumentChunk objects, each containing a portion of the text
        with preserved line numbers

    Note:
        The overlap ensures continuity for citations that span multiple lines
        or appear near chunk boundaries.
    """

    if max_lines <= 0:
        raise ValueError("max_lines must be a positive integer")
    if overlap < 0:
        raise ValueError("overlap cannot be negative")
    if overlap >= max_lines:
        raise ValueError("overlap must be smaller than max_lines")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    chunks: list[DocumentChunk] = []
    start = 0
    index = 0

    while start < len(lines):
        end = min(len(lines), start + max_lines)
        numbered_lines = [
            f"{line_no:04d}: {line}".rstrip()
            for line_no, line in enumerate(lines[start:end], start=start + 1)
        ]
        chunk_text = "\n".join(numbered_lines).strip()
        chunks.append(DocumentChunk(index=index, start_line=start + 1, end_line=end, text=chunk_text))
        if end == len(lines):
            break
        start = max(end - overlap, start + 1)
        index += 1

    return chunks


def annotate_document(text: str) -> str:
    """Add line numbers to an entire document.

    Prepends a 4-digit line number to each line of the document in the format
    "NNNN: content". This allows the agent to reference specific lines when
    reporting citations.

    Args:
        text: The raw document text

    Returns:
        The document with line numbers prefixed to each line

    Example:
        >>> annotate_document("Line one\\nLine two")
        '0001: Line one\\n0002: Line two'
    """

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(f"{idx+1:04d}: {line}".rstrip() for idx, line in enumerate(normalized.split("\n")))


def summarize_chunks(chunks: Iterable[DocumentChunk], *, limit: int = 5) -> str:
    """Generate a compact summary listing the first few chunks.

    Creates a preview of the document structure by listing the first N chunks
    with their section numbers, line ranges, and content previews. This is
    useful for giving the agent an overview of the document structure.

    Args:
        chunks: Iterable of DocumentChunk objects to summarize
        limit: Maximum number of chunks to include in the summary (default: 5)

    Returns:
        A formatted string with bullet points describing each chunk

    Example:
        >>> chunks = [DocumentChunk(0, 1, 10, "0001: Brief text...")]
        >>> print(summarize_chunks(chunks))
        - Section 0 (lines 1-10): Brief text...
    """

    rows = []
    for chunk in list(chunks)[:limit]:
        rows.append(
            f"- Section {chunk.index} (lines {chunk.start_line}-{chunk.end_line}): {chunk.preview}"
        )
    if not rows:
        return "- Section 0: <document was empty>"
    return "\n".join(rows)
