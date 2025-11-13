"""High-level orchestration for running the citation agent from the CLI.

This module provides the core service layer that coordinates:
    - Document loading and preprocessing
    - Agent initialization and configuration
    - Tool setup (document navigation + optional web search)
    - Agent execution and result extraction

The main entry point is CitationAgentService.run(), which handles the complete
workflow from raw document to structured CitationVerificationReport.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agents import Agent, ModelSettings, RunConfig, RunContextWrapper, Runner, WebSearchTool

from .document import annotate_document, chunk_document, load_document_text, summarize_chunks
from .models import CitationVerificationReport
from .tools import BriefContext, get_brief_section, list_brief_sections, search_brief_sections


@dataclass(slots=True)
class AgentConfig:
    """Runtime configuration for the citation agent.

    Attributes:
        model: OpenAI model identifier (e.g., 'gpt-4.1-mini', 'o4-mini')
        temperature: Sampling temperature (0.0-1.0), lower is more deterministic
        max_turns: Maximum reasoning iterations before timing out
        enable_web_search: Whether to provide the agent with web search capability
    """

    model: str = "gpt-4.1-mini"
    temperature: float = 0.1
    max_turns: int = 8
    enable_web_search: bool = True


class CitationAgentService:
    """Main service for running citation verification on legal documents.

    This service orchestrates the complete citation verification workflow:
    1. Loads and preprocesses the document
    2. Chunks it into manageable sections
    3. Configures the OpenAI agent with custom tools
    4. Runs the agent to analyze all citations
    5. Returns a structured verification report

    The service uses the OpenAI Agents SDK to provide the model with:
        - Custom tools for navigating the document
        - Optional web search for verifying citations
        - Structured output enforcement via Pydantic models
    """

    def __init__(self, config: AgentConfig | None = None) -> None:
        """Initialize the service with runtime configuration.

        Args:
            config: Agent configuration settings. If None, uses defaults.
        """
        self.config = config or AgentConfig()

    def run(self, brief_path: Path) -> CitationVerificationReport:
        """Run citation verification on a legal document.

        This is the main entry point that processes a document end-to-end.

        Args:
            brief_path: Path to the legal brief or memo to analyze

        Returns:
            A structured CitationVerificationReport containing all findings

        Raises:
            FileNotFoundError: If the document doesn't exist
            RuntimeError: If required libraries (PDF/Word) are not installed
            ValueError: If the file format is not supported

        Note:
            The agent may make multiple LLM calls and use web search to verify
            citations. Processing time varies with document length and complexity.
        """

        text = load_document_text(brief_path)
        return self.run_from_text(text, document_name=brief_path.name)

    def run_from_text(self, text: str, *, document_name: str = "pasted-text") -> CitationVerificationReport:
        """Run citation verification on an in-memory string.

        Args:
            text: Complete document text to evaluate.
            document_name: Friendly name to display in the final report.

        Returns:
            A structured CitationVerificationReport containing all findings.
        """

        return self._execute(text=text, document_name=document_name)

    def _execute(self, *, text: str, document_name: str) -> CitationVerificationReport:
        """Internal helper that executes the agent workflow."""

        chunks = chunk_document(text)
        overview = summarize_chunks(chunks, limit=6)
        annotated_text = annotate_document(text)
        context = BriefContext(document_name=document_name, chunks=chunks, overview=overview)

        agent = self._build_agent()
        agent_input = self._build_agent_input(context, annotated_text)

        result = Runner.run_sync(
            agent,
            agent_input,
            context=context,
            max_turns=self.config.max_turns,
            run_config=RunConfig(model=self.config.model),
        )
        return result.final_output_as(CitationVerificationReport, raise_if_incorrect_type=True)

    def _build_agent(self) -> Agent[BriefContext]:
        """Build and configure the OpenAI agent.

        Creates the 'CiteShield' agent with:
            - Custom instructions for citation verification
            - Document navigation tools (list, get, search)
            - Optional web search capability
            - Structured output type (CitationVerificationReport)

        Returns:
            A configured Agent instance ready to analyze documents

        Note:
            The agent uses dynamic instructions that incorporate the document
            name and chunk count from the runtime context.
        """

        tools = [list_brief_sections, get_brief_section, search_brief_sections]
        if self.config.enable_web_search:
            tools.append(WebSearchTool())

        def _instructions(ctx_wrapper: RunContextWrapper[BriefContext], _agent) -> str:
            ctx = ctx_wrapper.context
            return (
                "You are 'CiteShield', an exacting legal citation auditor. "
                f"The user uploaded '{ctx.document_name}', chunked into {len(ctx.chunks)} sections "
                "accessible through your tools. Extract each unique case, statute, regulation, or "
                "secondary authority cited in the document. For every citation you must: "
                "1) Restate the proposition credited to it, 2) confirm whether the authority truly "
                "supports it by reading the brief and, if necessary, searching the open web, and "
                "3) mark hallucinations or weak support so the drafter can fix them. "
                "Never invent citations; if you cannot find an authority after diligent searching, "
                "set verification_status to 'not_found' and explain the gap. "
                "Every output must conform to the CitationVerificationReport schema exactly."
            )

        return Agent(
            name="cite-shield",
            instructions=_instructions,
            tools=tools,
            model=self.config.model,
            model_settings=ModelSettings(temperature=self.config.temperature),
            output_type=CitationVerificationReport,
        )

    def _build_agent_input(self, context: BriefContext, annotated_text: str) -> str:
        """Construct the initial prompt for the agent.

        Builds a comprehensive prompt that includes:
            - Document metadata (name, section count)
            - Overview of document structure
            - Full document text with line numbers
            - Instructions for thorough verification

        Args:
            context: BriefContext containing document chunks and metadata
            annotated_text: Complete document with line numbers

        Returns:
            A formatted prompt string for the agent

        Note:
            The full annotated document is included to ensure the agent has
            complete context, while tools allow efficient section-by-section analysis.
        """

        return (
            f"You are reviewing the document '{context.document_name}'.\n"
            f"There are {len(context.chunks)} numbered sections. "
            "Use the provided tools to step through each section before drawing conclusions.\n\n"
            "Document overview:\n"
            f"{context.overview}\n\n"
            "Full document with line numbers:\n"
            "<<<DOCUMENT_START>>>\n"
            f"{annotated_text}\n"
            "<<<DOCUMENT_END>>>\n\n"
            "Deliver a comprehensive CitationVerificationReport. "
            "Only mark overall_assessment as 'pass' if every citation is verified. "
            "Flag anything uncertain as needs_review or not_found."
        )
