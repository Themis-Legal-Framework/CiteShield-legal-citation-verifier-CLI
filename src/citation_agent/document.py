"""Utilities for loading and chunking uploaded briefs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class DocumentChunk:
    """Represents a contiguous block of the source document with original line numbers."""

    index: int
    start_line: int
    end_line: int
    text: str

    @property
    def preview(self) -> str:
        snippet = self.text.splitlines()
        joined = " ".join(line.split(":", 1)[-1].strip() for line in snippet[:3])
        return (joined[:160] + "...") if len(joined) > 160 else joined


def load_document_text(path: Path) -> str:
    """Return unicode text for the supported file."""

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
    """Split text into overlapping windows while preserving original line numbers."""

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
    """Return the entire document with prefixed line numbers."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(f"{idx+1:04d}: {line}".rstrip() for idx, line in enumerate(normalized.split("\n")))


def summarize_chunks(chunks: Iterable[DocumentChunk], *, limit: int = 5) -> str:
    """Return a compact summary string that lists the first few chunks."""

    rows = []
    for chunk in list(chunks)[:limit]:
        rows.append(
            f"- Section {chunk.index} (lines {chunk.start_line}-{chunk.end_line}): {chunk.preview}"
        )
    if not rows:
        return "- Section 0: <document was empty>"
    return "\n".join(rows)
