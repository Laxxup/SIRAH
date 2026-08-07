"""Tests for OllamaIntelligence adapter."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sirah.errors import (
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
    IntelligenceUnavailableError,
    InvalidIntelligenceResponseError,
)
from sirah.intelligence.ollama_adapter import OllamaIntelligence
from sirah.types import ConversationMessage, IntelligenceRequest


def _user_message(text: str) -> ConversationMessage:
    return ConversationMessage(role="user", content=text)


def _request(messages: list[ConversationMessage] | None = None) -> IntelligenceRequest:
    return IntelligenceRequest(
        messages=tuple(messages or [_user_message("hola")]),
        system_prompt_override=None,
    )


def _json_response(text: str) -> str:
    return json.dumps({
        "message": {
            "content": json.dumps({"text_response": text, "capability_name": None, "capability_params": {}})
        }
    })


class _MockResponse:
    def __init__(self, status: int, body: str | dict | None = None, raise_on_read: Exception | None = None):
        self.status = status
        self._body = body
        self._raise = raise_on_read

    async def json(self):
        if self._raise:
            raise self._raise
        if isinstance(self._body, str):
            return json.loads(self._body)
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _MockSession:
    def __init__(self, responses: list[_MockResponse]):
        self._responses = list(responses)
        self.post_calls: list[dict] = []

    def post(self, url: str, json: dict | None = None):
        self.post_calls.append({"url": url, "json": json})
        resp = self._responses.pop(0)
        return resp

    def get(self, url: str):
        resp = self._responses.pop(0)
        return resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _patch_session(responses: list[_MockResponse]):
    session = _MockSession(responses)
    return patch("aiohttp.ClientSession", return_value=session), session


class TestOllamaDecidePrimary:
    @pytest.mark.asyncio
    async def test_primary_model_works(self) -> None:
        body = json.dumps({"message": {"content": '{"text_response": "¡Hola!", "capability_name": null, "capability_params": {}}'}})
        patcher, session = _patch_session([_MockResponse(200, body)])
        with patcher:
            adapter = OllamaIntelligence(model="gpt-oss:120b-cloud")
            resp = await adapter.decide(_request())
        assert resp.decision is not None
        assert resp.decision.text_response == "¡Hola!"
        assert resp.model == "gpt-oss:120b-cloud"
        assert resp.latency_ms >= 0
        assert session.post_calls[0]["json"]["model"] == "gpt-oss:120b-cloud"

    @pytest.mark.asyncio
    async def test_system_prompt_override_used(self) -> None:
        body = json.dumps({"message": {"content": '{"text_response": "ok", "capability_name": null, "capability_params": {}}'}})
        patcher, session = _patch_session([_MockResponse(200, body)])
        with patcher:
            adapter = OllamaIntelligence()
            req = _request()
            req = IntelligenceRequest(
                messages=req.messages,
                system_prompt_override="Eres SIRAH, sé breve.",
            )
            await adapter.decide(req)
        sent_messages = session.post_calls[0]["json"]["messages"]
        assert sent_messages[0]["role"] == "system"
        assert "SIRAH" in sent_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_timeout_raises_typed_error(self) -> None:
        def _timeout_post(*args, **kwargs):
            raise TimeoutError("connection timed out")

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.post = _timeout_post
            mock_cls.return_value = mock_session
            adapter = OllamaIntelligence(model="m", timeout=1.0)
            with pytest.raises(IntelligenceTimeoutError):
                await adapter.decide(_request())

    @pytest.mark.asyncio
    async def test_ollama_unavailable_raises(self) -> None:
        patcher, _ = _patch_session([_MockResponse(500)])
        with patcher:
            adapter = OllamaIntelligence(model="m", fallback_model=None)
            with pytest.raises(IntelligenceUnavailableError, match="server error"):
                await adapter.decide(_request())

    @pytest.mark.asyncio
    async def test_rate_limit_raises_without_fallback(self) -> None:
        patcher, _ = _patch_session([_MockResponse(429)])
        with patcher:
            adapter = OllamaIntelligence(model="m", fallback_model=None)
            with pytest.raises(IntelligenceRateLimitError):
                await adapter.decide(_request())

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_fallback(self) -> None:
        patcher, session = _patch_session([
            _MockResponse(429),
            _MockResponse(200, json.dumps({"message": {"content": '{"text_response": "degrado", "capability_name": null, "capability_params": {}}'}})),
        ])
        with patcher:
            adapter = OllamaIntelligence(model="cloud", fallback_model="gemma3:4b")
            resp = await adapter.decide(_request())
        assert resp.decision.text_response == "degrado"
        assert resp.model == "gemma3:4b"
        assert len(session.post_calls) == 2

    @pytest.mark.asyncio
    async def test_unstructured_text_response_is_graceful(self) -> None:
        body = json.dumps({"message": {"content": "Hola, soy SIRAH en texto libre"}})
        patcher, _ = _patch_session([_MockResponse(200, body)])
        with patcher:
            adapter = OllamaIntelligence(model="m")
            resp = await adapter.decide(_request())
        assert resp.decision is not None
        assert resp.decision.confidence == 0.7
        assert resp.decision.text_response == "Hola, soy SIRAH en texto libre"

    @pytest.mark.asyncio
    async def test_malformed_json_raises_invalid_response(self) -> None:
        body = json.dumps({"message": {"content": '{"content": "sin campo text_response"}'}})
        patcher, _ = _patch_session([_MockResponse(200, body)])
        with patcher:
            adapter = OllamaIntelligence(model="m", fallback_model=None)
            with pytest.raises(InvalidIntelligenceResponseError, match="sin campo text_response"):
                await adapter.decide(_request())


class TestOllamaFallback:
    @pytest.mark.asyncio
    async def test_primary_fails_falls_back_to_local(self) -> None:
        fail_body = _MockResponse(503)
        ok_body = _MockResponse(200, json.dumps({"message": {"content": '{"text_response": "respaldo", "capability_name": null, "capability_params": {}}'}}))
        patcher, session = _patch_session([fail_body, ok_body])
        with patcher:
            adapter = OllamaIntelligence(model="cloud-model", fallback_model="gemma3:4b")
            resp = await adapter.decide(_request())
        assert resp.decision.text_response == "respaldo"
        assert resp.model == "gemma3:4b"
        assert len(session.post_calls) == 2
        assert session.post_calls[0]["json"]["model"] == "cloud-model"
        assert session.post_calls[1]["json"]["model"] == "gemma3:4b"

    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self) -> None:
        ok_body = json.dumps({"message": {"content": '{"text_response": "fallback-ok", "capability_name": null, "capability_params": {}}'}})
        patcher, session = _patch_session([_MockResponse(200, ok_body)])

        call_count = 0
        original_post = _MockSession.post

        def _flaky_post(self, url, json=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("slow cloud")
            return original_post(self, url, json)

        with patch.object(_MockSession, "post", _flaky_post), patcher:
            adapter = OllamaIntelligence(model="cloud", fallback_model="gemma3:4b")
            resp = await adapter.decide(_request())
        assert resp.decision.text_response == "fallback-ok"
        assert resp.model == "gemma3:4b"

    @pytest.mark.asyncio
    async def test_fallback_also_fails_raises(self) -> None:
        patcher, _ = _patch_session([_MockResponse(503), _MockResponse(500)])
        with patcher:
            adapter = OllamaIntelligence(model="cloud", fallback_model="local")
            with pytest.raises(IntelligenceUnavailableError):
                await adapter.decide(_request())

    @pytest.mark.asyncio
    async def test_no_fallback_configured_raises_immediately(self) -> None:
        patcher, _ = _patch_session([_MockResponse(503)])
        with patcher:
            adapter = OllamaIntelligence(model="cloud", fallback_model=None)
            with pytest.raises(IntelligenceUnavailableError):
                await adapter.decide(_request())


class TestOllamaConfiguration:
    def test_default_model(self) -> None:
        adapter = OllamaIntelligence()
        assert adapter.primary_model == "gpt-oss:120b-cloud"
        assert adapter.fallback_model == "gemma3:4b"

    def test_custom_model(self) -> None:
        adapter = OllamaIntelligence(model="custom:7b", fallback_model="other:4b")
        assert adapter.primary_model == "custom:7b"
        assert adapter.fallback_model == "other:4b"

    def test_url_trailing_slash_stripped(self) -> None:
        adapter = OllamaIntelligence(base_url="http://host:11434/")
        assert adapter._base_url == "http://host:11434"


class TestOllamaNoSilentBugHiding:
    @pytest.mark.asyncio
    async def test_programming_error_not_hidden_by_fallback(self) -> None:
        def _bug(*args, **kwargs):
            raise RuntimeError("unexpected bug in adapter")

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.post = _bug
            mock_cls.return_value = mock_session
            adapter = OllamaIntelligence(model="cloud", fallback_model="local")
            with pytest.raises(RuntimeError):
                await adapter.decide(_request())

    @pytest.mark.asyncio
    async def test_malformed_response_raises_unavailable(self) -> None:
        patcher, _ = _patch_session([_MockResponse(200, '{"bad": "structure"}')])
        with patcher:
            adapter = OllamaIntelligence(model="m")
            with pytest.raises(IntelligenceUnavailableError, match="malformed"):
                await adapter.decide(_request())
