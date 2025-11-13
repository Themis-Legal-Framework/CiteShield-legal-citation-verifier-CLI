from __future__ import annotations

import csv

from citation_agent.models import CitationAssessment, CitationVerificationReport
from citation_agent.report_exporter import ReportExporter


def _sample_report() -> CitationVerificationReport:
    return CitationVerificationReport(
        document_name="trial-brief.pdf",
        overall_assessment="needs_review",
        total_citations=2,
        verified_citations=1,
        flagged_citations=1,
        unable_to_locate=0,
        narrative_summary="The filing raises a few questions about supporting authority.",
        citations=[
            CitationAssessment(
                citation_text="Roe v. Wade, 410 U.S. 113 (1973)",
                citation_type="case",
                proposition_summary="Establishes a privacy right.",
                verification_status="verified",
                reasoning="Primary source confirms the statement.",
                supporting_authorities=[
                    "https://supreme.justia.com/cases/federal/us/410/113/",
                    "Official reporter citation",
                ],
                risk_level="low",
                recommended_fix=None,
            ),
            CitationAssessment(
                citation_text="Imaginary Statute § 42",
                citation_type="statute",
                proposition_summary="Creates a right to unlimited vacation.",
                verification_status="contradicted",
                reasoning="No such statute exists.",
                supporting_authorities=[],
                risk_level="high",
                recommended_fix="Remove the citation.",
            ),
        ],
    )


def test_html_exporter_includes_sections_and_links(tmp_path):
    report = _sample_report()
    exporter = ReportExporter(report)

    html_path = tmp_path / "report.html"
    exporter.write_html(html_path)

    contents = html_path.read_text(encoding="utf-8")
    assert "<h2>Report Summary</h2>" in contents
    assert "<h2>Narrative Summary</h2>" in contents
    assert "<table class=\"citations\">" in contents
    assert "href=\"https://supreme.justia.com/cases/federal/us/410/113/\"" in contents
    assert "No supporting evidence provided." in contents


def test_csv_exporter_outputs_summary_and_rows(tmp_path):
    report = _sample_report()
    exporter = ReportExporter(report)

    csv_path = tmp_path / "report.csv"
    exporter.write_csv(csv_path)

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert rows[0] == ["document_name", "trial-brief.pdf"]
    assert rows[1] == ["overall_assessment", "needs_review"]
    header_index = rows.index(
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
    first_data_row = rows[header_index + 1]
    assert first_data_row[1] == "Roe v. Wade, 410 U.S. 113 (1973)"
    assert "https://supreme.justia.com" in first_data_row[-1]


def test_default_basename_sanitizes_document_name():
    assert ReportExporter.default_basename("A Brief.docx") == "a-brief"
    assert ReportExporter.default_basename("stdin") == "stdin"
    assert ReportExporter.default_basename(" ") == "citation-report"
