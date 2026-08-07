"""Test factory and system assembly."""

from __future__ import annotations

import pytest

from sirah.core.devices import DeviceRegistry
from sirah.core.runtime import SirahRuntime
from sirah.types import ClientKind, SpeechRecognitionEvent
from sirah.voice.diagnostics import AudioMetrics, AudioStage, CapturedAudio
from sirah.voice.simulated import FakeSpeechInput


@pytest.mark.asyncio
async def test_runtime_installs_and_calls_its_audio_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Capture:
        async def start(self) -> None:
            pass

        async def record(self) -> CapturedAudio:
            metrics = AudioMetrics(0, 0, 16_000, 1, 2, 0, 0, True)
            return CapturedAudio(b"", 16_000, 1, 2, 0, metrics)

        async def stop(self) -> None:
            pass

    monkeypatch.setattr("sirah.voice.stt_whisper.WhisperSTT", FakeSpeechInput)
    runtime = SirahRuntime(
        client_secrets={ClientKind.CLI: "cli-secret"},
        devices=DeviceRegistry(
            capture_devices=("runtime-mic",), capture_device="runtime-mic"
        ),
        capture_factory=lambda _device: Capture(),
    )

    await runtime.start()
    try:
        result = await runtime.submit_local_voice_turn()
        assert result.turn_id
        assert result.stage is AudioStage.SILENCE
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_uses_only_registry_configured_capture_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected: list[str] = []

    class Capture:
        async def start(self) -> None:
            pass

        async def record(self) -> CapturedAudio:
            metrics = AudioMetrics(0, 0, 16_000, 1, 2, 0, 0, True)
            return CapturedAudio(b"", 16_000, 1, 2, 0, metrics)

        async def stop(self) -> None:
            pass

    def make_capture(device: str) -> Capture:
        selected.append(device)
        return Capture()

    monkeypatch.setattr("sirah.voice.stt_whisper.WhisperSTT", FakeSpeechInput)
    runtime = SirahRuntime(
        client_secrets={ClientKind.CLI: "cli-secret"},
        devices=DeviceRegistry(
            capture_devices=("mic-a", "mic-b"), capture_device="mic-b"
        ),
        capture_factory=make_capture,
    )
    await runtime.start()
    try:
        result = await runtime.submit_local_voice_turn()
        assert selected == ["mic-b"]
        assert result.stage is AudioStage.SILENCE
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_constructs_one_capture_per_local_voice_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures: list[Capture] = []

    class Capture:
        def __init__(self) -> None:
            self.records = 0

        async def start(self) -> None:
            pass

        async def record(self) -> CapturedAudio:
            self.records += 1
            metrics = AudioMetrics(0, 0, 16_000, 1, 2, 0, 0, True)
            return CapturedAudio(b"", 16_000, 1, 2, 0, metrics)

        async def stop(self) -> None:
            pass

    def make_capture(_: str) -> Capture:
        capture = Capture()
        captures.append(capture)
        return capture

    monkeypatch.setattr("sirah.voice.stt_whisper.WhisperSTT", FakeSpeechInput)
    runtime = SirahRuntime(
        client_secrets={ClientKind.CLI: "cli-secret"},
        devices=DeviceRegistry(capture_devices=("mic",), capture_device="mic"),
        capture_factory=make_capture,
    )
    await runtime.start()
    try:
        await runtime.submit_local_voice_turn()
        await runtime.submit_local_voice_turn()
        assert len(captures) == 2
        assert [capture.records for capture in captures] == [1, 1]
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_uses_one_persistent_whisper_recognizer_for_two_local_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recognizers: list[FakeWhisper] = []

    class FakeWhisper:
        def __init__(self) -> None:
            self.model_loads = 0
            self.transcriptions: list[tuple[bytes, str]] = []
            recognizers.append(self)

        async def start(self) -> None:
            self.model_loads += 1

        async def transcribe(self, wav: bytes, turn_id: str) -> SpeechRecognitionEvent:
            self.transcriptions.append((wav, turn_id))
            return SpeechRecognitionEvent("hola", True)

        async def health(self) -> bool:
            return self.model_loads == 1

        async def stop(self) -> None:
            pass

    class Capture:
        async def start(self) -> None:
            pass

        async def record(self) -> CapturedAudio:
            metrics = AudioMetrics(4, 0, 16_000, 1, 2, 1_000, 1_000, False)
            return CapturedAudio(b"captured-wav", 16_000, 1, 2, 0, metrics)

        async def stop(self) -> None:
            pass

    monkeypatch.setattr("sirah.voice.stt_whisper.WhisperSTT", FakeWhisper)
    runtime = SirahRuntime(
        client_secrets={ClientKind.CLI: "cli-secret"},
        devices=DeviceRegistry(capture_devices=("mic",), capture_device="mic"),
        capture_factory=lambda _device: Capture(),
    )

    await runtime.start()
    try:
        first = await runtime.submit_local_voice_turn()
        second = await runtime.submit_local_voice_turn()
    finally:
        await runtime.stop()

    recognizer = recognizers[0]
    assert len(recognizers) == 1
    assert recognizer.model_loads == 1
    assert [wav for wav, _ in recognizer.transcriptions] == [b"captured-wav"] * 2
    assert [turn_id for _, turn_id in recognizer.transcriptions] == [
        first.turn_id,
        second.turn_id,
    ]
    assert first.stage is AudioStage.COMPLETED
    assert second.stage is AudioStage.COMPLETED
