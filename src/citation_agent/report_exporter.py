"""Utilities for exporting citation verification reports."""
from __future__ import annotations

import csv
import re
from html import escape
from io import StringIO
from pathlib import Path
from typing import Iterable

from .models import CitationAssessment, CitationVerificationReport


class ReportExporter:
    """Serialize :class:`CitationVerificationReport` into rich document formats."""

    def __init__(self, report: CitationVerificationReport) -> None:
        self.report = report

    @staticmethod
    def default_basename(document_name: str) -> str:
        """Return a filesystem-friendly base name derived from the document name."""

        base = Path(document_name).stem or document_name
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-_")
        return slug.lower() or "citation-report"

    def to_html(self) -> str:
        """Render the report as a standalone HTML document."""

        report = self.report
        title = f"Citation Verification Report - {escape(report.document_name)}"
        summary_rows = "".join(
            _summary_row(label, value, highlight)
            for label, value, highlight in [
                ("Document", report.document_name, False),
                ("Overall Assessment", report.overall_assessment, True),
                ("Total Citations", report.total_citations, False),
                ("Verified Citations", report.verified_citations, False),
                ("Flagged Citations", report.flagged_citations, False),
                ("Unable to Locate", report.unable_to_locate, False),
            ]
        )
        narrative = _format_paragraph(report.narrative_summary)

        if report.citations:
            citation_rows = "".join(
                _citation_row(index + 1, citation) for index, citation in enumerate(report.citations)
            )
            citation_table = f"""
            <table class=\"citations\">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Citation</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Risk</th>
                        <th>Proposition Summary</th>
                        <th>Reasoning</th>
                        <th>Recommended Fix</th>
                        <th>Supporting Evidence</th>
                    </tr>
                </thead>
                <tbody>
                    {citation_rows}
                </tbody>
            </table>
            """
        else:
            citation_table = """
            <p class=\"empty-state\">No citations were included in this report.</p>
            """

        return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            margin: 2rem;
            line-height: 1.5;
            color: #1f2933;
            background: #f9fafb;
        }}
        h1, h2 {{
            color: #0b7285;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 2rem;
            background: #fff;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.12);
        }}
        table th, table td {{
            padding: 0.75rem;
            border-bottom: 1px solid #e2e8f0;
            vertical-align: top;
        }}
        table th {{
            text-align: left;
            background: #e7f5ff;
            font-weight: 600;
        }}
        .summary-table {{
            width: auto;
        }}
        .summary-table th {{
            width: 16rem;
        }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 999px;
            font-size: 0.85rem;
            background: #f1f5f9;
            color: #0f172a;
        }}
        .badge.pass {{ background: #c8e6c9; color: #1b5e20; }}
        .badge.needs_review {{ background: #fff3bf; color: #8a6d3b; }}
        .badge.high_risk {{ background: #ffcdd2; color: #b71c1c; }}
        .badge.verified {{ background: #c8e6c9; color: #1b5e20; }}
        .badge.not_found {{ background: #ffe8cc; color: #7f4f24; }}
        .badge.contradicted {{ background: #f8d7da; color: #842029; }}
        .empty-state {{
            font-style: italic;
            color: #64748b;
        }}
        ul.supporting {{
            margin: 0;
            padding-left: 1.5rem;
        }}
        ul.supporting li {{
            margin-bottom: 0.35rem;
        }}
        a {{
            color: #0b7285;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <section>
        <h2>Report Summary</h2>
        <table class=\"summary-table\">
            <tbody>
                {summary_rows}
            </tbody>
        </table>
    </section>
    <section>
        <h2>Narrative Summary</h2>
        {narrative}
    </section>
    <section>
        <h2>Citation Details</h2>
        {citation_table}
    </section>
</body>
</html>
"""

    def to_csv(self) -> str:
        """Render the report as CSV (including summary metadata)."""

        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["document_name", self.report.document_name])
        writer.writerow(["overall_assessment", self.report.overall_assessment])
        writer.writerow(["total_citations", self.report.total_citations])
        writer.writerow(["verified_citations", self.report.verified_citations])
        writer.writerow(["flagged_citations", self.report.flagged_citations])
        writer.writerow(["unable_to_locate", self.report.unable_to_locate])
        writer.writerow(["narrative_summary", self.report.narrative_summary])
        writer.writerow([])
        writer.writerow(
            [
                "index",
                "citation_text",
                "citation_type",
                "verification_status",
                "risk_level",
                "proposition_summary",
                "reasoning",
                "recommended_fix",
                "supporting_authorities",
            ]
        )
        for index, citation in enumerate(self.report.citations, 1):
            writer.writerow(
                [
                    index,
                    citation.citation_text,
                    citation.citation_type,
                    citation.verification_status,
                    citation.risk_level,
                    citation.proposition_summary,
                    citation.reasoning,
                    citation.recommended_fix or "",
                    " | ".join(citation.supporting_authorities),
                ]
            )
        return buffer.getvalue()

    def write_html(self, path: Path) -> Path:
        """Write the HTML export to ``path`` and return it."""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_html(), encoding="utf-8")
        return path

    def write_csv(self, path: Path) -> Path:
        """Write the CSV export to ``path`` and return it."""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_csv(), encoding="utf-8")
        return path


def _summary_row(label: str, value: object, highlight: bool = False) -> str:
    formatted_value = _format_summary_value(value, highlight)
    return """
        <tr>
            <th>{}</th>
            <td>{}</td>
        </tr>
    """.format(escape(str(label)), formatted_value)


def _format_summary_value(value: object, highlight: bool) -> str:
    if isinstance(value, str):
        if highlight:
            badge_class = value.replace(" ", "_")
            label = value.replace("_", " ").title()
            return f'<span class="badge {badge_class}">{escape(label)}</span>'
        return escape(value)
    if isinstance(value, (int, float)):
        return escape(str(value))
    return escape(repr(value))


def _format_paragraph(text: str) -> str:
    paragraphs = [escape(part) for part in text.splitlines() if part.strip()]
    if not paragraphs:
        return '<p class="empty-state">No narrative summary provided.</p>'
    return "\n".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)


def _citation_row(index: int, citation: CitationAssessment) -> str:
    supporting = _format_supporting(citation.supporting_authorities)
    badge_class = citation.verification_status.replace(" ", "_")
    return f"""
        <tr>
            <td>{index}</td>
            <td>{escape(citation.citation_text)}</td>
            <td>{escape(citation.citation_type)}</td>
            <td><span class=\"badge {badge_class}\">{escape(citation.verification_status)}</span></td>
            <td>{escape(citation.risk_level)}</td>
            <td>{escape(citation.proposition_summary)}</td>
            <td>{escape(citation.reasoning)}</td>
            <td>{escape(citation.recommended_fix or '—')}</td>
            <td>{supporting}</td>
        </tr>
    """


def _format_supporting(authorities: Iterable[str]) -> str:
    items = []
    for authority in authorities:
        authority = authority.strip()
        if not authority:
            continue
        escaped = escape(authority)
        if _looks_like_url(authority):
            items.append(
                f'<li><a href="{escaped}" target="_blank" rel="noopener noreferrer">{escaped}</a></li>'
            )
        else:
            items.append(f"<li>{escaped}</li>")
    if not items:
        return '<span class="empty-state">No supporting evidence provided.</span>'
    return '<ul class="supporting">' + "".join(items) + "</ul>"


def _looks_like_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))
