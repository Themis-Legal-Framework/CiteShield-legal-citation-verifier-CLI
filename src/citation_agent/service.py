"""High-level orchestration for running the citation agent from the CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agents import Agent, ModelSettings, RunConfig, RunContextWrapper, Runner, WebSearchTool

from .document import annotate_document, chunk_document, load_document_text, summarize_chunks
from .models import CitationVerificationReport
from .tools import BriefContext, get_brief_section, list_brief_sections, search_brief_sections


@dataclass(slots=True)
class AgentConfig:
    """Runtime knobs for the CLI."""

    model: str = "gpt-4.1-mini"
    temperature: float = 0.1
    max_turns: int = 8
    enable_web_search: bool = True


class CitationAgentService:
    """Loads a brief, wires up the OpenAI agent, and returns the structured report."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()

    def run(self, brief_path: Path) -> CitationVerificationReport:
        """Entry point used by the CLI."""

        text = load_document_text(brief_path)
        chunks = chunk_document(text)
        overview = summarize_chunks(chunks, limit=6)
        annotated_text = annotate_document(text)
        context = BriefContext(document_name=brief_path.name, chunks=chunks, overview=overview)

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
        """Instantiate the OpenAI agent with instructions and the available tools."""

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
        """Prepare the string passed as the user's message to the agent."""

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
