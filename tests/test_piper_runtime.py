"""Persistent Piper synthesis and runtime-owned playback."""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path

import pytest

from sirah.errors import SpeechError, SpeechUnavailableError
from sirah.types import SpeechRecognitionEvent
from sirah.voice.audio_service import AudioTurnService
from sirah.voice.coordinator import AudioTurnCoordinator
from sirah.voice.diagnostics import AudioStage
from sirah.voice.tts_piper import AplayPlayer, PiperTTS


class Player:
    def __init__(self, result: bool = True) -> None:
        self._result = result

    async def play(self, wav_path: Path) -> bool:
        assert wav_path.exists()
        return self._result


@pytest.mark.asyncio
async def test_piper_loads_one_model_for_two_synthesis_operations(tmp_path: Path) -> None:
    loads = 0

    class Model:
        def synthesize_wav(self, text: str, output: wave.Wave_write) -> None:
            assert text in {"uno", "dos"}
            output.writeframes(b"wav")

    def load_model(model_path: Path, config_path: Path) -> Model:
        nonlocal loads
        assert model_path == tmp_path / "voice.onnx"
        assert config_path == tmp_path / "voice.onnx.json"
        loads += 1
        return Model()

    output = PiperTTS(
        model_path=tmp_path / "voice.onnx",
        config_path=tmp_path / "voice.onnx.json",
        model_loader=load_model,
        player=Player(),
        temp_dir=tmp_path,
    )

    await output.start()
    assert (await output.speak("uno")).success
    assert (await output.speak("dos")).success
    assert loads == 1
    assert list(tmp_path.glob("*.wav")) == []
    assert await output.health() is True


@pytest.mark.asyncio
async def test_piper_synthesis_failure_is_typed_and_unhealthy(tmp_path: Path) -> None:
    class Model:
        def synthesize_wav(self, text: str, output: wave.Wave_write) -> None:
            del text, output
            raise RuntimeError("model failure")

    output = PiperTTS(
        model_path=tmp_path / "voice.onnx",
        config_path=tmp_path / "voice.onnx.json",
        model_loader=lambda _model, _config: Model(),
        player=Player(),
        temp_dir=tmp_path,
    )

    await output.start()
    with pytest.raises(SpeechError, match="Piper synthesis failed"):
        await output.speak("private text")

    assert await output.health() is False
    assert "private text" not in str(vars(output))
    assert list(tmp_path.glob("*.wav")) == []


@pytest.mark.asyncio
async def test_piper_model_load_failure_is_typed_and_degrades_health(tmp_path: Path) -> None:
    failures = 0

    def record_failure() -> None:
        nonlocal failures
        failures += 1

    output = PiperTTS(
        model_path=tmp_path / "voice.onnx",
        config_path=tmp_path / "voice.onnx.json",
        model_loader=lambda _model, _config: (_ for _ in ()).throw(RuntimeError()),
        player=Player(),
        on_failure=record_failure,
    )

    with pytest.raises(SpeechUnavailableError, match="Piper model unavailable"):
        await output.start()

    assert await output.health() is False
    assert failures == 1


@pytest.mark.asyncio
async def test_aplay_timeout_terminates_its_child_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    released = asyncio.Event()

    class Process:
        terminated = False

        async def wait(self) -> int:
            await released.wait()
            return 0

        def terminate(self) -> None:
            self.terminated = True
            released.set()

    process = Process()

    async def create_process(*args: object, **kwargs: object) -> Process:
        del args, kwargs
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    assert await AplayPlayer("default", timeout_s=0.01).play(tmp_path / "voice.wav") is False
    assert process.terminated


@pytest.mark.asyncio
async def test_aplay_cancellation_terminates_its_child_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    waiting = asyncio.Event()
    released = asyncio.Event()

    class Process:
        terminated = False

        async def wait(self) -> int:
            waiting.set()
            await released.wait()
            return 0

        def terminate(self) -> None:
            self.terminated = True
            released.set()

    process = Process()

    async def create_process(*args: object, **kwargs: object) -> Process:
        del args, kwargs
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    task = asyncio.create_task(AplayPlayer("default").play(tmp_path / "voice.wav"))
    await waiting.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.terminated


@pytest.mark.asyncio
async def test_piper_playback_failure_returns_unsuccessful_completion(tmp_path: Path) -> None:
    class Model:
        def synthesize_wav(self, text: str, output: wave.Wave_write) -> None:
            del text
            output.writeframes(b"wav")

    output = PiperTTS(
        model_path=tmp_path / "voice.onnx",
        config_path=tmp_path / "voice.onnx.json",
        model_loader=lambda _model, _config: Model(),
        player=Player(result=False),
        temp_dir=tmp_path,
    )

    await output.start()
    completion = await output.speak("hola")

    assert completion.success is False
    assert await output.health() is False
    assert list(tmp_path.glob("*.wav")) == []


@pytest.mark.asyncio
async def test_piper_synthesis_failure_releases_human_audio_lease(tmp_path: Path) -> None:
    class Model:
        def synthesize_wav(self, text: str, output: wave.Wave_write) -> None:
            del text, output
            raise RuntimeError("model failure")

    class Recognizer:
        async def transcribe(self, wav: bytes, turn_id: str) -> SpeechRecognitionEvent:
            del wav, turn_id
            return SpeechRecognitionEvent("hola", True)

    output = PiperTTS(
        model_path=tmp_path / "voice.onnx",
        config_path=tmp_path / "voice.onnx.json",
        model_loader=lambda _model, _config: Model(),
        player=Player(),
        temp_dir=tmp_path,
    )
    await output.start()
    coordinator = AudioTurnCoordinator()
    service = AudioTurnService(
        capture_device="configured-capture",
        recognizer=Recognizer(),
        speech_output=output,
        coordinator=coordinator,
        respond=lambda _text: _response(),
    )

    result = await service.submit_human_turn()

    assert result.stage is AudioStage.TTS_FAILED
    assert coordinator.is_free


async def _response() -> str:
    return "respuesta privada"
