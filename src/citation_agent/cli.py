"""Command-line entry point exposed via `citation-agent`."""

from __future__ import annotations

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
    file: Annotated[Path, typer.Argument(help="Path to the brief or memo (txt, md, pdf, docx).")],
    model: Annotated[str, typer.Option(help="OpenAI model identifier.")] = "gpt-4.1-mini",
    temperature: Annotated[float, typer.Option(min=0.0, max=1.0)] = 0.1,
    max_turns: Annotated[int, typer.Option(help="Max reasoning turns before aborting.")] = 8,
    web_search: Annotated[bool, typer.Option(help="Allow the agent to search the open web.")] = True,
    output: Annotated[Literal["table", "json"], typer.Option(help="Choose JSON for raw output.")] = "table",
) -> None:
    """Run the agent against the supplied document."""

    config = AgentConfig(
        model=model,
        temperature=temperature,
        max_turns=max_turns,
        enable_web_search=web_search,
    )
    service = CitationAgentService(config=config)

    try:
        report = service.run(file)
    except FileNotFoundError as exc:
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
    """Describe the built-in tools the agent can rely on."""

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
