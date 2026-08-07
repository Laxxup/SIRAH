"""Tests for KokoroHTTPTTS adapter."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sirah.errors import (
    SpeechBusyError,
    SpeechError,
    SpeechUnavailableError,
    TTSInvalidAudioError,
)


def _make_wav_bytes(duration_s: float = 0.1, sample_rate: int = 24000) -> bytes:
    """Generate a minimal valid WAV file in memory."""
    num_frames = int(sample_rate * duration_s)
    samples = b"\x00\x00" * num_frames
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples)
    return buf.getvalue()


class _MockResponse:
    def __init__(
        self,
        status: int,
        body: bytes = b"",
        content_type: str = "audio/wav",
        raise_on_read: Exception | None = None,
    ):
        self.status = status
        self._body = body
        self._raise = raise_on_read
        self.headers = {"content-type": content_type}

    async def read(self):
        if self._raise:
            raise self._raise
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
        return self._responses.pop(0)

    def get(self, url: str):
        return self._responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _patch_session(responses: list[_MockResponse]):
    session = _MockSession(responses)
    return patch("aiohttp.ClientSession", return_value=session), session


class _StubPlayer:
    def __init__(self, should_succeed: bool = True) -> None:
        self._succeed = should_succeed
        self.play_calls: list[Path] = []

    async def play(self, wav_path: Path) -> bool:
        self.play_calls.append(wav_path)
        return self._succeed


def _adapter(player=None, **kwargs):
    from sirah.voice.tts_kokoro import KokoroHTTPTTS
    if player is None:
        player = _StubPlayer()
    defaults = dict(base_url="http://127.0.0.1:8880/v1", player=player)
    defaults.update(kwargs)
    return KokoroHTTPTTS(**defaults)


class TestKokoroHappyPath:
    @pytest.mark.asyncio
    async def test_successful_synthesis(self, tmp_path: Path) -> None:
        wav = _make_wav_bytes()
        patcher, session = _patch_session([_MockResponse(200, wav)])
        player = _StubPlayer()
        with patcher:
            adapter = _adapter(player=player, temp_dir=tmp_path)
            result = await adapter.speak("Hola mundo")
        assert result.success is True
        assert result.operation_id
        assert result.duration_ms >= 0
        assert len(player.play_calls) == 1
        assert len(session.post_calls) == 1

    @pytest.mark.asyncio
    async def test_uses_configured_model(self) -> None:
        wav = _make_wav_bytes()
        patcher, session = _patch_session([_MockResponse(200, wav)])
        with patcher:
            adapter = _adapter(model="custom-model")
            await adapter.speak("test")
        assert session.post_calls[0]["json"]["model"] == "custom-model"

    @pytest.mark.asyncio
    async def test_uses_configured_voice(self) -> None:
        wav = _make_wav_bytes()
        patcher, session = _patch_session([_MockResponse(200, wav)])
        with patcher:
            adapter = _adapter(voice="af_alloy")
            await adapter.speak("test")
        assert session.post_calls[0]["json"]["voice"] == "af_alloy"

    @pytest.mark.asyncio
    async def test_uses_configured_speed(self) -> None:
        wav = _make_wav_bytes()
        patcher, session = _patch_session([_MockResponse(200, wav)])
        with patcher:
            adapter = _adapter(speed=1.5)
            await adapter.speak("test")
        assert session.post_calls[0]["json"]["speed"] == 1.5

    @pytest.mark.asyncio
    async def test_correct_endpoint_and_payload(self) -> None:
        wav = _make_wav_bytes()
        patcher, session = _patch_session([_MockResponse(200, wav)])
        with patcher:
            adapter = _adapter(base_url="http://host:8880/v1")
            await adapter.speak("texto de prueba")
        call = session.post_calls[0]
        assert call["url"] == "http://host:8880/v1/audio/speech"
        assert call["json"]["input"] == "texto de prueba"
        assert call["json"]["response_format"] == "wav"


class TestKokoroHttpErrors:
    @pytest.mark.asyncio
    async def test_500_raises_unavailable(self) -> None:
        patcher, _ = _patch_session([_MockResponse(500)])
        with patcher:
            adapter = _adapter()
            with pytest.raises(SpeechUnavailableError, match="server error"):
                await adapter.speak("hola")

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit(self) -> None:
        patcher, _ = _patch_session([_MockResponse(429)])
        with patcher:
            adapter = _adapter()
            with pytest.raises(SpeechUnavailableError, match="rate limited"):
                await adapter.speak("hola")

    @pytest.mark.asyncio
    async def test_non_200_raises(self) -> None:
        patcher, _ = _patch_session([_MockResponse(404)])
        with patcher:
            adapter = _adapter()
            with pytest.raises(SpeechUnavailableError, match="HTTP 404"):
                await adapter.speak("hola")

    @pytest.mark.asyncio
    async def test_connection_error_raises(self) -> None:
        def _fail(*args, **kwargs):
            raise ConnectionRefusedError("connection refused")

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.post = _fail
            mock_cls.return_value = mock_session
            adapter = _adapter()
            with pytest.raises(SpeechUnavailableError, match="connection error"):
                await adapter.speak("hola")


class TestKokoroInvalidAudio:
    @pytest.mark.asyncio
    async def test_empty_body_raises_invalid_audio(self) -> None:
        patcher, _ = _patch_session([_MockResponse(200, b"")])
        with patcher:
            adapter = _adapter()
            with pytest.raises(TTSInvalidAudioError, match="empty body"):
                await adapter.speak("hola")

    @pytest.mark.asyncio
    async def test_json_instead_of_wav_raises(self) -> None:
        body = json.dumps({"error": "model not found"}).encode()
        patcher, _ = _patch_session([_MockResponse(200, body, "application/json")])
        with patcher:
            adapter = _adapter()
            with pytest.raises(TTSInvalidAudioError, match="JSON instead of WAV"):
                await adapter.speak("hola")

    @pytest.mark.asyncio
    async def test_wrong_content_type_raises(self) -> None:
        wav = _make_wav_bytes()
        patcher, _ = _patch_session([_MockResponse(200, wav, "text/html")])
        with patcher:
            adapter = _adapter()
            with pytest.raises(TTSInvalidAudioError, match="unexpected content-type"):
                await adapter.speak("hola")

    @pytest.mark.asyncio
    async def test_no_wav_header_raises(self) -> None:
        patcher, _ = _patch_session([_MockResponse(200, b"NOTAWAVFILE!!!")])
        with patcher:
            adapter = _adapter()
            with pytest.raises(TTSInvalidAudioError, match="without WAV header"):
                await adapter.speak("hola")


class TestKokoroConfiguration:
    def test_default_voice_is_ef_dora(self) -> None:
        from sirah.voice.tts_kokoro import KokoroHTTPTTS
        adapter = KokoroHTTPTTS(base_url="http://x", player=_StubPlayer())
        assert adapter.voice == "ef_dora"

    def test_custom_voice(self) -> None:
        adapter = _adapter(voice="af_bella")
        assert adapter.voice == "af_bella"

    def test_url_trailing_slash_stripped(self) -> None:
        adapter = _adapter(base_url="http://host:8880/v1/")
        assert adapter._base_url == "http://host:8880/v1"


class TestKokoroBusyState:
    @pytest.mark.asyncio
    async def test_busy_raises(self) -> None:
        wav = _make_wav_bytes(duration_s=10)
        patcher, _ = _patch_session([_MockResponse(200, wav)])
        adapter = _adapter()

        async def _long_call():
            await adapter.speak("first")

        import asyncio
        task = asyncio.create_task(_long_call())
        await asyncio.sleep(0.01)
        with pytest.raises(SpeechBusyError):
            await adapter.speak("second")
        await task


class TestKokoroNoSilentBugHiding:
    @pytest.mark.asyncio
    async def test_programming_error_not_hidden(self) -> None:
        def _bug(*args, **kwargs):
            raise RuntimeError("unexpected bug in adapter")

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.post = _bug
            mock_cls.return_value = mock_session
            adapter = _adapter()
            with pytest.raises(SpeechError, match="unexpected bug"):
                await adapter.speak("hola")


class TestKokoroPlayerFailure:
    @pytest.mark.asyncio
    async def test_player_fails_returns_unsuccessful(self) -> None:
        wav = _make_wav_bytes()
        patcher, _ = _patch_session([_MockResponse(200, wav)])
        player = _StubPlayer(should_succeed=False)
        with patcher:
            adapter = _adapter(player=player)
            result = await adapter.speak("hola")
        assert result.success is False


class TestKokoroProperties:
    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        patcher, _ = _patch_session([_MockResponse(200)])
        with patcher:
            adapter = _adapter()
            assert await adapter.health() is True

    @pytest.mark.asyncio
    async def test_health_check_fail(self) -> None:
        patcher, _ = _patch_session([_MockResponse(500)])
        with patcher:
            adapter = _adapter()
            assert await adapter.health() is False
