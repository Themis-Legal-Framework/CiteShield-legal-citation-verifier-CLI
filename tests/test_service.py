from pathlib import Path

import pytest

from citation_agent.models import CitationVerificationReport
from citation_agent.service import AgentConfig, CitationAgentService


class DummyResult:
    def final_output_as(self, cls, raise_if_incorrect_type=True):
        return cls(
            document_name="brief.txt",
            overall_assessment="pass",
            total_citations=1,
            verified_citations=1,
            flagged_citations=0,
            unable_to_locate=0,
            narrative_summary="All good.",
            citations=[],
        )


@pytest.fixture
def dummy_service(monkeypatch):
    svc = CitationAgentService(AgentConfig(enable_web_search=False))
    monkeypatch.setattr("citation_agent.service.Runner.run_sync", lambda *a, **kw: DummyResult())
    return svc


def test_run_returns_report(tmp_path: Path, dummy_service: CitationAgentService):
    path = tmp_path / "brief.txt"
    path.write_text("Brown v. Board of Education, 347 U.S. 483 (1954)")
    report = dummy_service.run(path)
    assert isinstance(report, CitationVerificationReport)
    assert report.overall_assessment == "pass"


def test_run_from_text_returns_report(dummy_service: CitationAgentService):
    report = dummy_service.run_from_text("Marbury v. Madison", document_name="inline")
    assert isinstance(report, CitationVerificationReport)
    assert report.overall_assessment == "pass"
