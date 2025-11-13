from __future__ import annotations

from typer.testing import CliRunner

from citation_agent import cli
from citation_agent.models import CitationVerificationReport


def test_verify_runtime_error_exit(monkeypatch, tmp_path):
    failing_message = "Service boom"

    class FailingService:
        def __init__(self, config):  # pragma: no cover - simple stub
            pass

        def run(self, file_path):
            raise RuntimeError(failing_message)

    monkeypatch.setattr(cli, "CitationAgentService", FailingService)

    document_path = tmp_path / "brief.txt"
    document_path.write_text("Example content")

    runner = CliRunner()
    result = runner.invoke(cli.app, ["verify", str(document_path)])

    assert result.exit_code == 1
    assert failing_message in result.stdout


def test_verify_accepts_inline_text(monkeypatch):
    captured: dict[str, tuple[str, str]] = {}

    class RecordingService:
        def __init__(self, config):  # pragma: no cover - simple stub
            pass

        def run(self, file_path):  # pragma: no cover - unused in this test
            raise AssertionError("run() should not be called when --text is provided")

        def run_from_text(self, text, document_name="pasted-text"):
            captured["args"] = (text, document_name)
            return CitationVerificationReport(
                document_name=document_name,
                overall_assessment="needs_review",
                total_citations=0,
                verified_citations=0,
                flagged_citations=0,
                unable_to_locate=0,
                narrative_summary="",
                citations=[],
            )

    monkeypatch.setattr(cli, "CitationAgentService", RecordingService)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["verify", "--text", "Example citation"])

    assert result.exit_code == 0
    assert captured["args"] == ("Example citation", "inline-text")


def test_verify_reads_from_stdin(monkeypatch):
    captured: dict[str, tuple[str, str]] = {}

    class RecordingService:
        def __init__(self, config):  # pragma: no cover - simple stub
            pass

        def run(self, file_path):  # pragma: no cover - unused in this test
            raise AssertionError("run() should not be called for stdin")

        def run_from_text(self, text, document_name="pasted-text"):
            captured["args"] = (text, document_name)
            return CitationVerificationReport(
                document_name=document_name,
                overall_assessment="needs_review",
                total_citations=0,
                verified_citations=0,
                flagged_citations=0,
                unable_to_locate=0,
                narrative_summary="",
                citations=[],
            )

    monkeypatch.setattr(cli, "CitationAgentService", RecordingService)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["verify", "-"], input="Example citation from stdin")

    assert result.exit_code == 0
    assert captured["args"] == ("Example citation from stdin", "stdin")
