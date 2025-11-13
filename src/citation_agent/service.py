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

import inspect
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from agents import Agent, ModelSettings, RunConfig, RunContextWrapper, Runner, WebSearchTool
from agents.lifecycle import RunHooksBase
from agents.items import ModelResponse

from .document import annotate_document, chunk_document, load_document_text, summarize_chunks
from .models import CitationVerificationReport
from .tools import (
    AuthorityLookupClient,
    BriefContext,
    get_brief_section,
    list_brief_sections,
    lookup_authority,
    search_brief_sections,
)


AUTHORITY_LOOKUP_API_KEY_ENV = "CITESHIELD_AUTHORITY_LOOKUP_API_KEY"
AUTHORITY_LOOKUP_BASE_URL_ENV = "CITESHIELD_AUTHORITY_LOOKUP_BASE_URL"
DEFAULT_AUTHORITY_LOOKUP_API_KEY = os.getenv(AUTHORITY_LOOKUP_API_KEY_ENV)
DEFAULT_AUTHORITY_LOOKUP_BASE_URL = os.getenv(AUTHORITY_LOOKUP_BASE_URL_ENV)


@dataclass(slots=True)
class AgentConfig:
    """Runtime configuration for the citation agent.

    Attributes:
        model: OpenAI model identifier (e.g., 'gpt-4.1-mini', 'o4-mini')
        temperature: Sampling temperature (0.0-1.0), lower is more deterministic
        max_turns: Maximum reasoning iterations before timing out
        enable_web_search: Whether to provide the agent with web search capability
        enable_authority_lookup: Enable the external legal authority lookup tool
        authority_lookup_api_key: API key used to authenticate with the lookup service
        authority_lookup_base_url: Endpoint URL for the legal authority lookup service
        authority_lookup_timeout: Request timeout (seconds) for the lookup service
    """

    model: str = "gpt-4.1-mini"
    temperature: float = 0.1
    max_turns: int = 8
    enable_web_search: bool = True
    enable_authority_lookup: bool = bool(DEFAULT_AUTHORITY_LOOKUP_BASE_URL)
    authority_lookup_api_key: str | None = DEFAULT_AUTHORITY_LOOKUP_API_KEY
    authority_lookup_base_url: str | None = DEFAULT_AUTHORITY_LOOKUP_BASE_URL
    authority_lookup_timeout: float = 10.0


logger = logging.getLogger(__name__)


ProgressEventType = Literal[
    "agent_start",
    "agent_end",
    "llm_start",
    "llm_end",
    "tool_start",
    "tool_end",
    "handoff",
]


@dataclass(slots=True)
class ProgressEvent:
    """Lightweight notification payload for agent lifecycle events."""

    event: ProgressEventType
    agent_name: str | None
    turn: int | None = None
    payload: dict[str, Any] | None = None


ProgressCallback = Callable[[ProgressEvent], None | Awaitable[None]]


class _ProgressRunHooks(RunHooksBase[BriefContext, Agent[BriefContext]]):
    """Forward key agent lifecycle events to an observer callback."""

    def __init__(self, callback: ProgressCallback) -> None:
        self._callback = callback
        self._turn = 0

    async def _emit(
        self,
        *,
        event: ProgressEventType,
        agent: Agent[BriefContext],
        turn: int | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        progress_event = ProgressEvent(
            event=event,
            agent_name=_safe_agent_name(agent),
            turn=turn,
            payload=payload or None,
        )
        try:
            result = self._callback(progress_event)
            if inspect.isawaitable(result):
                await result
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Progress callback failed during %s", event)

    async def on_agent_start(
        self,
        context: RunContextWrapper[BriefContext],
        agent: Agent[BriefContext],
    ) -> None:
        self._turn += 1
        payload = {
            "document_name": context.context.document_name,
            "chunk_count": len(context.context.chunks),
        }
        await self._emit(event="agent_start", agent=agent, turn=self._turn, payload=payload)

    async def on_agent_end(
        self,
        context: RunContextWrapper[BriefContext],
        agent: Agent[BriefContext],
        output: Any,
    ) -> None:
        payload = {"output_type": type(output).__name__}
        await self._emit(event="agent_end", agent=agent, turn=self._turn, payload=payload)

    async def on_llm_start(
        self,
        context: RunContextWrapper[BriefContext],
        agent: Agent[BriefContext],
        system_prompt: str | None,
        input_items: list[Any],
    ) -> None:
        payload = {
            "system_prompt": system_prompt,
            "input_count": len(input_items),
        }
        await self._emit(event="llm_start", agent=agent, turn=self._turn, payload=payload)

    async def on_llm_end(
        self,
        context: RunContextWrapper[BriefContext],
        agent: Agent[BriefContext],
        response: ModelResponse,
    ) -> None:
        payload = _extract_response_payload(response)
        await self._emit(event="llm_end", agent=agent, turn=self._turn, payload=payload)

    async def on_tool_start(
        self,
        context: RunContextWrapper[BriefContext],
        agent: Agent[BriefContext],
        tool: Any,
    ) -> None:
        payload = {"tool_name": getattr(tool, "name", type(tool).__name__)}
        await self._emit(event="tool_start", agent=agent, turn=self._turn, payload=payload)

    async def on_tool_end(
        self,
        context: RunContextWrapper[BriefContext],
        agent: Agent[BriefContext],
        tool: Any,
        result: str,
    ) -> None:
        payload = {
            "tool_name": getattr(tool, "name", type(tool).__name__),
            "result": result,
        }
        await self._emit(event="tool_end", agent=agent, turn=self._turn, payload=payload)

    async def on_handoff(
        self,
        context: RunContextWrapper[BriefContext],
        from_agent: Agent[BriefContext],
        to_agent: Agent[BriefContext],
    ) -> None:
        payload = {"to_agent": _safe_agent_name(to_agent)}
        await self._emit(event="handoff", agent=from_agent, turn=self._turn, payload=payload)


def _safe_agent_name(agent: Agent[BriefContext]) -> str:
    return getattr(agent, "name", agent.__class__.__name__)


def _extract_response_payload(response: ModelResponse) -> dict[str, Any]:
    """Extract reasoning traces and assistant messages for observers."""

    reasoning_lines: list[str] = []
    messages: list[str] = []

    for item in response.output:
        item_type = getattr(item, "type", None)
        if item_type == "reasoning":
            contents = getattr(item, "content", None) or []
            for content in contents:
                text = getattr(content, "text", None)
                if text:
                    reasoning_lines.append(text)
        elif item_type == "message":
            for content in getattr(item, "content", []):
                if getattr(content, "type", None) == "output_text":
                    text = getattr(content, "text", None)
                    if text:
                        messages.append(text)

    payload: dict[str, Any] = {}
    if reasoning_lines:
        payload["reasoning"] = reasoning_lines
    if messages:
        payload["messages"] = messages
    return payload


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

    def __init__(
        self,
        config: AgentConfig | None = None,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Initialize the service with runtime configuration.

        Args:
            config: Agent configuration settings. If None, uses defaults.
        """
        self.config = config or AgentConfig()
        self._progress_callback = progress_callback

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
        authority_client = self._build_authority_lookup_client()
        context = BriefContext(
            document_name=document_name,
            chunks=chunks,
            overview=overview,
            authority_lookup_client=authority_client,
        )

        agent = self._build_agent()
        agent_input = self._build_agent_input(context, annotated_text)

        hooks = _ProgressRunHooks(self._progress_callback) if self._progress_callback else None

        result = Runner.run_sync(
            agent,
            agent_input,
            context=context,
            max_turns=self.config.max_turns,
            hooks=hooks,
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
        lookup_enabled, _, lookup_base_url, _ = self._resolve_authority_lookup_config()
        if lookup_enabled and lookup_base_url:
            tools.append(lookup_authority)
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
                "supports it by reading the brief and, if necessary, searching the open web or your legal database tools, and "
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

    def _resolve_authority_lookup_config(self) -> tuple[bool, str | None, str | None, float]:
        env_api_key = os.getenv(AUTHORITY_LOOKUP_API_KEY_ENV)
        env_base_url = os.getenv(AUTHORITY_LOOKUP_BASE_URL_ENV)
        base_url = self.config.authority_lookup_base_url or env_base_url
        api_key = self.config.authority_lookup_api_key or env_api_key

        if self.config.enable_authority_lookup is False:
            enabled = False
        else:
            enabled = bool(self.config.enable_authority_lookup) or bool(base_url)
        return enabled, api_key, base_url, self.config.authority_lookup_timeout

    def _build_authority_lookup_client(self) -> AuthorityLookupClient | None:
        enabled, api_key, base_url, timeout = self._resolve_authority_lookup_config()
        if not enabled or not base_url:
            return None
        return AuthorityLookupClient(base_url=base_url, api_key=api_key, timeout=timeout)

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
