import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents import RunContextWrapper
from agents.items import ModelResponse
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText
from openai.types.responses.response_reasoning_item import (
    Content,
    ResponseReasoningItem,
    Summary,
)

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


def test_progress_callback_receives_events(monkeypatch):
    captured_events = []

    def progress(event):
        captured_events.append(event)

    service = CitationAgentService(AgentConfig(enable_web_search=False), progress_callback=progress)

    def fake_run_sync(
        agent,
        agent_input,
        *,
        context,
        max_turns,
        hooks=None,
        run_config=None,
        **kwargs,
    ):
        assert hooks is not None

        async def trigger_events():
            wrapper = RunContextWrapper(context)
            await hooks.on_agent_start(wrapper, agent)
            await hooks.on_llm_start(wrapper, agent, None, [])

            reasoning_item = ResponseReasoningItem(
                id="r1",
                type="reasoning",
                summary=[Summary(text="Summary", type="summary_text")],
                content=[Content(text="Thinking through the citation", type="reasoning_text")],
                status="completed",
            )
            message_item = ResponseOutputMessage(
                id="m1",
                role="assistant",
                status="completed",
                type="message",
                content=[ResponseOutputText(type="output_text", text="Final verdict", annotations=[])],
            )
            response = ModelResponse(output=[reasoning_item, message_item], usage=Usage(), response_id=None)
            await hooks.on_llm_end(wrapper, agent, response)

            tool = SimpleNamespace(name="search_brief_sections")
            await hooks.on_tool_start(wrapper, agent, tool)
            await hooks.on_tool_end(wrapper, agent, tool, "Snippet of text")
            await hooks.on_agent_end(wrapper, agent, "done")

        asyncio.run(trigger_events())
        return DummyResult()

    monkeypatch.setattr("citation_agent.service.Runner.run_sync", fake_run_sync)

    report = service.run_from_text("Sample citation", document_name="inline")

    assert isinstance(report, CitationVerificationReport)
    assert report.overall_assessment == "pass"
    assert any(event.event == "tool_start" for event in captured_events)
    llm_event = next((event for event in captured_events if event.event == "llm_end"), None)
    assert llm_event is not None
    assert llm_event.payload is not None and "reasoning" in llm_event.payload
