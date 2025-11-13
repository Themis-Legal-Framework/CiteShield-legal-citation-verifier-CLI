import json

from agents import RunContextWrapper

from citation_agent.document import DocumentChunk
from citation_agent.tools import (
    AuthorityLookupClient,
    AuthorityLookupError,
    BriefContext,
    list_brief_sections_impl,
    lookup_authority_impl,
    search_brief_sections_impl,
)


def test_list_sections_returns_preview():
    chunks = [DocumentChunk(index=0, start_line=1, end_line=3, text="0001: Hello world")]
    ctx = RunContextWrapper(context=BriefContext(document_name="x", chunks=chunks))
    result = list_brief_sections_impl(ctx)
    assert "Section 0" in result


def test_search_sections_finds_keyword():
    chunks = [
        DocumentChunk(index=0, start_line=1, end_line=2, text="Case Brown v. Board"),
        DocumentChunk(index=1, start_line=3, end_line=4, text="Random text"),
    ]
    ctx = RunContextWrapper(context=BriefContext(document_name="x", chunks=chunks))
    res = search_brief_sections_impl(ctx, query="Brown")
    assert "Section 0" in res


def test_lookup_authority_returns_unavailable_when_disabled():
    ctx = RunContextWrapper(context=BriefContext(document_name="x"))
    result = lookup_authority_impl(ctx, citation="Brown v. Board")
    payload = json.loads(result)
    assert payload["status"] == "unavailable"


def test_lookup_authority_returns_payload(monkeypatch):
    class StubClient:
        def lookup(self, citation, jurisdiction=None):
            assert jurisdiction == "US"
            return {
                "authority_name": "Brown v. Board",
                "citation": citation,
                "jurisdiction": jurisdiction,
                "snippets": ["Holding snippet"],
                "metadata": {"source": "stub"},
            }

    ctx = RunContextWrapper(
        context=BriefContext(
            document_name="x",
            authority_lookup_client=StubClient(),
        )
    )

    result = lookup_authority_impl(ctx, citation="Brown v. Board", jurisdiction="US")
    payload = json.loads(result)
    assert payload["status"] == "ok"
    assert payload["data"]["authority_name"] == "Brown v. Board"
    assert payload["data"]["snippets"] == ["Holding snippet"]


def test_lookup_authority_handles_errors():
    class FailingClient:
        def lookup(self, citation, jurisdiction=None):
            raise AuthorityLookupError("Service unavailable")

    ctx = RunContextWrapper(
        context=BriefContext(
            document_name="x",
            authority_lookup_client=FailingClient(),
        )
    )

    result = lookup_authority_impl(ctx, citation="Brown v. Board")
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "Service unavailable" in payload["message"]


def test_lookup_authority_rejects_blank_input():
    ctx = RunContextWrapper(context=BriefContext(document_name="x"))
    result = lookup_authority_impl(ctx, citation="   ")
    payload = json.loads(result)
    assert payload["status"] == "error"


def test_authority_lookup_client_requests_api(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status = 200

        def read(self):
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "authority_name": "Example Authority",
                "citation": "347 U.S. 483",
                "jurisdiction": "US",
                "snippets": ["Key passage"],
            }
        )

    monkeypatch.setattr("citation_agent.tools.urlopen", fake_urlopen)

    client = AuthorityLookupClient(
        base_url="https://api.example.com/lookup",
        api_key="token-123",
        timeout=5.0,
    )

    data = client.lookup("Brown v. Board", jurisdiction="US")

    assert "citation=Brown+v.+Board" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer token-123"
    assert captured["timeout"] == 5.0
    assert data["authority_name"] == "Example Authority"
    assert data["jurisdiction"] == "US"


def test_authority_lookup_client_normalizes_snippets(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status = 200

        def read(self):
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        payload = {
            "authority_name": "Example Authority",
            "snippets": [
                {"text": " Primary holding. "},
                {"snippet": "Alternative phrasing"},
                {"content": ""},
                {"unused": "value"},
                42,
                None,
                "  trailing whitespace  ",
            ],
        }
        return FakeResponse(payload)

    monkeypatch.setattr("citation_agent.tools.urlopen", fake_urlopen)

    client = AuthorityLookupClient(base_url="https://api.example.com", api_key="token")
    data = client.lookup("Brown v. Board")

    assert data["snippets"] == [
        "Primary holding.",
        "Alternative phrasing",
        json.dumps({"unused": "value"}),
        "42",
        "trailing whitespace",
    ]
