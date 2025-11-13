"""Command-line entry point exposed via `citation-agent`.

This module provides the CLI interface for the CiteShield citation verification tool.
It uses Typer for command-line parsing and Rich for beautiful terminal output.

Available Commands:
    verify: Run citation verification on a legal document
    explain-tools: Display information about the agent's available tools

The main entry point is the `verify` command, which processes a document and
outputs either a formatted table or JSON report of citation verification results.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import CitationAssessment, CitationVerificationReport
from .service import AgentConfig, CitationAgentService

app = typer.Typer(help="Vet legal briefs for hallucinated citations using OpenAI agents.")
console = Console()


@app.command()
def verify(
    file: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the brief or memo (txt, md, pdf, docx). Use '-' to read from stdin.",
        ),
    ] = None,
    text: Annotated[
        str | None,
        typer.Option(
            "--text",
            help="Provide raw document text directly via the command line.",
        ),
    ] = None,
    model: Annotated[str, typer.Option(help="OpenAI model identifier.")] = "gpt-4.1-mini",
    temperature: Annotated[float, typer.Option(min=0.0, max=1.0)] = 0.1,
    max_turns: Annotated[int, typer.Option(help="Max reasoning turns before aborting.")] = 8,
    web_search: Annotated[bool, typer.Option(help="Allow the agent to search the open web.")] = True,
    output: Annotated[Literal["table", "json"], typer.Option(help="Choose JSON for raw output.")] = "table",
) -> None:
    """Verify citations in a legal document using AI.

    This command processes a legal brief or memo, extracting all citations and
    verifying their accuracy using an OpenAI agent. The agent:
        1. Identifies all legal citations in the document
        2. Checks if each citation supports its claimed proposition
        3. Uses web search (optional) to verify citations
        4. Provides a detailed report with recommendations

    Args:
        file: Path to the document file (.txt, .md, .pdf, or .docx). Use '-' to read from stdin.
        text: Raw document text provided inline via --text
        model: OpenAI model to use (e.g., 'gpt-4.1-mini', 'o4-mini')
        temperature: Sampling temperature (0.0-1.0), lower is more deterministic
        max_turns: Maximum number of agent reasoning iterations
        web_search: Enable web search for citation verification
        output: Output format - 'table' for formatted display, 'json' for machine-readable

    Returns:
        None. Outputs results to stdout and exits with code 0 on success,
        1 on file error, or 2 on agent error.

    Examples:
        # Basic verification with default settings
        $ citation-agent verify brief.txt

        # Paste text via stdin (press Ctrl-D to finish on macOS/Linux)
        $ citation-agent verify -

        # Provide inline text without creating a file
        $ citation-agent verify --text "Roe v. Wade..."

        # Use a specific model with JSON output
        $ citation-agent verify brief.pdf --model gpt-4.1 --output json

        # Disable web search and increase max turns
        $ citation-agent verify memo.docx --no-web-search --max-turns 12

    Note:
        Requires OPENAI_API_KEY environment variable to be set.
    """

    if file is None and text is None:
        raise typer.BadParameter("Provide a document path or use --text / '-' for stdin input.")
    if file is not None and text is not None:
        raise typer.BadParameter("Cannot supply both a file path and --text.")

    config = AgentConfig(
        model=model,
        temperature=temperature,
        max_turns=max_turns,
        enable_web_search=web_search,
    )
    service = CitationAgentService(config=config)

    try:
        if text is not None:
            if not text.strip():
                raise ValueError("Provided --text input is empty.")
            report = service.run_from_text(text, document_name="inline-text")
        else:
            assert file is not None
            if str(file) == "-":
                stdin_text = sys.stdin.read()
                if not stdin_text.strip():
                    raise ValueError("No input received from stdin.")
                report = service.run_from_text(stdin_text, document_name="stdin")
            else:
                report = service.run(file)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except (RuntimeError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # pragma: no cover - defensive
        typer.secho(f"Agent run failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=2) from exc

    if output == "json":
        typer.echo(report.model_dump_json(indent=2))
        return

    _render_report(report)


@app.command("explain-tools")
def explain_tools() -> None:
    """Display information about the agent's available tools.

    Prints a formatted table describing each tool that the CiteShield agent
    can use during citation verification. This helps users understand how
    the agent navigates and analyzes documents.

    Tools include:
        - list_brief_sections: Browse document structure
        - get_brief_section: Read specific sections
        - search_brief_sections: Find relevant passages
        - web_search: Verify citations online (optional)
    """

    rows = [
        ("list_brief_sections", "Quick index of document sections, accepts pagination arguments."),
        ("get_brief_section", "Returns verbatim text (with line numbers) for a section."),
        ("search_brief_sections", "Keyword search to find relevant passages."),
        ("web_search", "Hosted OpenAI tool to look up cases/statutes on the public web (optional)."),
    ]
    table = Table(title="Available Tools", show_lines=True)
    table.add_column("Tool", style="cyan", no_wrap=True)
    table.add_column("What it does", style="white")
    for name, description in rows:
        table.add_row(name, description)
    console.print(table)


def _render_report(report: CitationVerificationReport) -> None:
    """Render a citation verification report to the terminal.

    Creates a formatted display using Rich library components:
        1. Summary panel with overall statistics
        2. Narrative summary panel
        3. Detailed table of individual citations

    Args:
        report: The CitationVerificationReport to display

    Note:
        This function is called internally when output format is 'table'.
        For 'json' output, the report is serialized directly.
    """
    header = Table(show_header=False, box=None)
    header.add_row("Document", report.document_name)
    header.add_row("Overall", report.overall_assessment)
    header.add_row("Totals", str(report.total_citations))
    header.add_row("Verified", str(report.verified_citations))
    header.add_row("Flagged", str(report.flagged_citations))
    header.add_row("Not found", str(report.unable_to_locate))
    console.print(Panel(header, title="Citation Audit Summary", expand=False))
    console.print(Panel(report.narrative_summary, title="Narrative"))

    table = Table(title="Per-citation analysis", show_lines=True)
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Citation", style="green")
    table.add_column("Proposition", style="magenta")
    table.add_column("Status", style="yellow")
    table.add_column("Risk", style="red")
    table.add_column("Reasoning", style="white")

    for idx, citation in enumerate(report.citations, start=1):
        table.add_row(
            str(idx),
            citation.citation_text,
            citation.proposition_summary,
            citation.verification_status,
            citation.risk_level,
            citation.reasoning,
        )
    console.print(table)


if __name__ == "__main__":  # pragma: no cover
    app()
