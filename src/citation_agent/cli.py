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
from collections import deque
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import CitationAssessment, CitationVerificationReport
from .service import AgentConfig, CitationAgentService, ProgressEvent
from .report_exporter import ReportExporter

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
    export_html: Annotated[
        Path | None,
        typer.Option(
            "--export-html",
            help="Write an HTML report to the given file path.",
            dir_okay=False,
        ),
    ] = None,
    export_csv: Annotated[
        Path | None,
        typer.Option(
            "--export-csv",
            help="Write a CSV report to the given file path.",
            dir_okay=False,
        ),
    ] = None,
    export: Annotated[
        Path | None,
        typer.Option(
            "--export",
            help="Directory where both HTML and CSV exports should be written.",
            file_okay=False,
        ),
    ] = None,
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

        # Export structured reports alongside the console table
        $ citation-agent verify brief.txt --export reports/
    
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
    progress_renderer = _ProgressRenderer(console)
    service = CitationAgentService(config=config, progress_callback=progress_renderer)

    try:
        with Live(progress_renderer.render(), console=console, refresh_per_second=4) as live:
            progress_renderer.set_live(live)
            report = _run_service(service=service, file=file, text=text)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except (RuntimeError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # pragma: no cover - defensive
        typer.secho(f"Agent run failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=2) from exc
    finally:
        progress_renderer.set_live(None)

    _handle_exports(report, export_html=export_html, export_csv=export_csv, export_dir=export)

    if output == "json":
        typer.echo(report.model_dump_json(indent=2))
        return

    _render_report(report)


def _run_service(
    service: CitationAgentService,
    *,
    file: Path | None,
    text: str | None,
) -> CitationVerificationReport:
    """Execute the appropriate service entry point based on user input."""

    if text is not None:
        if not text.strip():
            raise ValueError("Provided --text input is empty.")
        return service.run_from_text(text, document_name="inline-text")

    assert file is not None
    if str(file) == "-":
        stdin_text = sys.stdin.read()
        if not stdin_text.strip():
            raise ValueError("No input received from stdin.")
        return service.run_from_text(stdin_text, document_name="stdin")

    return service.run(file)


def _handle_exports(
    report: CitationVerificationReport,
    *,
    export_html: Path | None,
    export_csv: Path | None,
    export_dir: Path | None,
) -> None:
    """Write report exports requested through CLI flags."""

    if not any((export_html, export_csv, export_dir)):
        return

    exporter = ReportExporter(report)
    messages: list[str] = []

    if export_dir is not None:
        export_dir.mkdir(parents=True, exist_ok=True)
        base = ReportExporter.default_basename(report.document_name)
        html_path = export_dir / f"{base}.html"
        csv_path = export_dir / f"{base}.csv"
        exporter.write_html(html_path)
        exporter.write_csv(csv_path)
        messages.append(f"HTML report -> {html_path}")
        messages.append(f"CSV report  -> {csv_path}")

    if export_html is not None:
        exporter.write_html(export_html)
        messages.append(f"HTML report -> {export_html}")

    if export_csv is not None:
        exporter.write_csv(export_csv)
        messages.append(f"CSV report  -> {export_csv}")

    if messages:
        formatted = "\n".join(messages)
        typer.secho(f"Saved report exports:\n{formatted}", fg=typer.colors.GREEN)


class _ProgressRenderer:
    """Render incremental agent updates using Rich live components."""

    def __init__(self, console: Console, max_events: int = 10) -> None:
        self.console = console
        self._events: deque[Text] = deque(maxlen=max_events)
        self._current_agent: str = "initializing"
        self._live: Live | None = None

    def set_live(self, live: Live | None) -> None:
        self._live = live
        if live is not None:
            live.update(self.render())

    def __call__(self, event: ProgressEvent) -> None:
        self._current_agent = event.agent_name or self._current_agent
        rendered = self._format_event(event)
        if rendered is not None:
            self._events.appendleft(rendered)
        if self._live is not None:
            self._live.update(self.render())

    def render(self) -> Panel:
        body = Table.grid(padding=(0, 1))
        body.add_column()
        if self._events:
            for line in self._events:
                body.add_row(line)
        else:
            body.add_row(Text("Waiting for agent activity...", style="dim"))
        header = Text(f"Active agent: {self._current_agent}", style="bold cyan")
        return Panel(Group(header, body), title="Agent progress", border_style="cyan", padding=(1, 1))

    def _format_event(self, event: ProgressEvent) -> Text | None:
        payload = event.payload or {}
        prefix = _turn_prefix(event)

        if event.event == "tool_start":
            message = f"{prefix}Calling tool [bold]{payload.get('tool_name', 'tool')}[/bold]"
            return Text.from_markup(message, style="yellow")
        if event.event == "tool_end":
            message = f"{prefix}Tool finished: [bold]{payload.get('tool_name', 'tool')}[/bold]"
            text = Text.from_markup(message, style="green")
            snippet = payload.get("result")
            if snippet:
                text.append(" → ", style="green")
                text.append(_truncate(snippet), style="dim")
            return text
        if event.event == "llm_start":
            message = f"{prefix}LLM call starting ({payload.get('input_count', 0)} inputs)"
            return Text.from_markup(message, style="cyan")
        if event.event == "llm_end":
            text = Text(prefix, style="magenta")
            if prefix:
                text.append("", style="magenta")
            reasoning = payload.get("reasoning")
            messages = payload.get("messages")
            parts: list[str] = []
            if reasoning:
                parts.append(f"Reasoning: {_truncate(reasoning[-1])}")
            if messages:
                parts.append(f"Reply: {_truncate(messages[-1])}")
            summary = " | ".join(parts) if parts else "LLM call completed"
            text.append(summary, style="magenta")
            return text
        if event.event == "agent_start":
            doc = payload.get("document_name", "document")
            chunk_count = payload.get("chunk_count")
            detail = f" ({chunk_count} chunks)" if chunk_count is not None else ""
            message = f"Starting analysis of [bold]{doc}[/bold]{detail}"
            return Text.from_markup(message, style="white")
        if event.event == "agent_end":
            message = f"{prefix}Agent completed ({payload.get('output_type', 'output')})"
            return Text.from_markup(message, style="green")
        if event.event == "handoff":
            message = f"{prefix}Handoff to [bold]{payload.get('to_agent', 'agent')}[/bold]"
            return Text.from_markup(message, style="blue")
        return None


def _turn_prefix(event: ProgressEvent) -> str:
    if event.turn is None:
        return ""
    return f"Turn {event.turn}: "


def _truncate(text: str, width: int = 80) -> str:
    display = text.strip()
    if len(display) > width:
        return display[: width - 1] + "…"
    return display


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
