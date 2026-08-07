"""AudioTurnService terminal results and leased local audio ownership."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from sirah.errors import (
    SpeechError,
    SpeechInputError,
    SpeechRecognitionError,
    SpeechRecognitionTimeoutError,
)
from sirah.types import SpeechCompletion, SpeechRecognitionEvent
from sirah.voice.audio_service import AudioTurnService
from sirah.voice.coordinator import AudioTurnCoordinator, AudioTurnDirection
from sirah.voice.diagnostics import AudioMetrics, AudioStage, CapturedAudio


class Input:
    def __init__(self, event: SpeechRecognitionEvent | Exception) -> None:
        self._event = event

    async def listen(self, timeout: float | None = None) -> SpeechRecognitionEvent:
        if isinstance(self._event, Exception):
            raise self._event
        return self._event

    async def transcribe(self, audio: bytes, turn_id: str) -> SpeechRecognitionEvent:
        del audio, turn_id
        return await self.listen()

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health(self) -> bool:
        return True


class Output:
    def __init__(self, result: SpeechCompletion | Exception) -> None:
        self._result = result
        self.spoken: list[str] = []

    async def speak(self, text: str) -> SpeechCompletion:
        self.spoken.append(text)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    async def stop(self) -> None:
        pass

    async def health(self) -> bool:
        return True


def completion(success: bool = True) -> SpeechCompletion:
    return SpeechCompletion(operation_id="output-1", success=success)


async def respond(text: str) -> str:
    return f"respuesta: {text}"


def service(
    event: SpeechRecognitionEvent | Exception,
    output: SpeechCompletion | Exception | None = None,
    responder: Callable[[str], Awaitable[str]] = respond,
) -> tuple[AudioTurnService, AudioTurnCoordinator, Output]:
    coordinator = AudioTurnCoordinator()
    speech_output = Output(completion() if output is None else output)
    return (
        AudioTurnService(
            capture_device="configured-capture",
            speech_input=Input(event),
            speech_output=speech_output,
            coordinator=coordinator,
            respond=responder,
        ),
        coordinator,
        speech_output,
    )


@pytest.mark.asyncio
async def test_human_turn_returns_generated_id_and_completed_terminal_result() -> None:
    audio, coordinator, output = service(SpeechRecognitionEvent("hola", True))

    result = await audio.submit_human_turn()

    assert result.turn_id
    assert result.stage is AudioStage.COMPLETED
    assert result.transcript == "hola"
    assert result.response == "respuesta: hola"
    assert result.tts_completion == completion()
    assert output.spoken == ["respuesta: hola"]
    assert coordinator.is_free


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "output", "responder", "stage"),
    [
        (SpeechInputError("recognizer lost"), completion(), respond, AudioStage.STT_FAILED),
        (SpeechRecognitionEvent("", False), completion(), respond, AudioStage.STT_EMPTY),
        (
            SpeechRecognitionEvent("hola", True),
            completion(),
            lambda _text: _raise(SpeechError("intelligence unavailable")),
            AudioStage.INTELLIGENCE_FAILED,
        ),
        (
            SpeechRecognitionEvent("hola", True),
            SpeechError("synthesis failed"),
            respond,
            AudioStage.TTS_FAILED,
        ),
        (
            SpeechRecognitionEvent("hola", True),
            completion(False),
            respond,
            AudioStage.PLAYBACK_FAILED,
        ),
    ],
)
async def test_human_turn_maps_each_failure_to_a_terminal_stage_and_releases_lease(
    event: SpeechRecognitionEvent | Exception,
    output: SpeechCompletion | Exception,
    responder: Callable[[str], Awaitable[str]],
    stage: AudioStage,
) -> None:
    audio, coordinator, _ = service(event, output, responder)

    result = await audio.submit_human_turn()

    assert result.stage is stage
    assert coordinator.is_free


async def _raise(error: Exception) -> str:
    raise error


@pytest.mark.asyncio
async def test_concurrent_human_turn_is_rejected_with_typed_terminal_stage() -> None:
    release_input = asyncio.Event()

    class BlockingInput(Input):
        async def listen(self, timeout: float | None = None) -> SpeechRecognitionEvent:
            await release_input.wait()
            return SpeechRecognitionEvent("hola", True)

    coordinator = AudioTurnCoordinator()
    audio = AudioTurnService(
        capture_device="configured-capture",
        speech_input=BlockingInput(SpeechRecognitionEvent("", False)),
        speech_output=Output(completion()),
        coordinator=coordinator,
        respond=respond,
    )
    first = asyncio.create_task(audio.submit_human_turn())
    await asyncio.sleep(0)

    rejected = await audio.submit_human_turn()
    release_input.set()
    await first

    assert rejected.stage is AudioStage.CAPTURE_FAILED
    assert coordinator.is_free


@pytest.mark.asyncio
async def test_human_input_blocks_autonomous_speech_until_its_lease_releases() -> None:
    audio, coordinator, output = service(SpeechRecognitionEvent("hola", True))
    lease = await coordinator.reserve(AudioTurnDirection.INPUT)

    waiting = asyncio.create_task(audio.speak_autonomously("autonomía"))
    await asyncio.sleep(0)

    assert not waiting.done()
    await coordinator.release(lease)
    completed = await waiting

    assert completed.stage is AudioStage.COMPLETED
    assert output.spoken == ["autonomía"]


@pytest.mark.asyncio
async def test_human_turn_preserves_mic_capture_metrics_in_its_terminal_result() -> None:
    metrics = AudioMetrics(320, 10, 16_000, 1, 2, 1_000, 2_000, False)

    class Capture:
        async def start(self) -> None:
            pass

        async def record(self) -> CapturedAudio:
            return CapturedAudio(b"wav", 16_000, 1, 2, 10, metrics)

        async def stop(self) -> None:
            pass

    coordinator = AudioTurnCoordinator()
    audio = AudioTurnService(
        capture_device="configured-capture",
        capture=Capture(),
        speech_input=Input(SpeechRecognitionEvent("hola", True)),
        speech_output=Output(completion()),
        coordinator=coordinator,
        respond=respond,
    )

    result = await audio.submit_human_turn()

    assert result.stage is AudioStage.COMPLETED
    assert result.diagnostics is metrics
    assert coordinator.is_free


@pytest.mark.asyncio
async def test_human_turn_waits_for_autonomous_output_instead_of_capture_failure() -> None:
    output_started = asyncio.Event()
    release_output = asyncio.Event()

    class BlockingOutput(Output):
        async def speak(self, text: str) -> SpeechCompletion:
            self.spoken.append(text)
            output_started.set()
            await release_output.wait()
            return completion()

    coordinator = AudioTurnCoordinator()
    audio = AudioTurnService(
        capture_device="configured-capture",
        speech_input=Input(SpeechRecognitionEvent("hola", True)),
        speech_output=BlockingOutput(completion()),
        coordinator=coordinator,
        respond=respond,
    )
    autonomous = asyncio.create_task(audio.speak_autonomously("autonomía"))
    await output_started.wait()
    human = asyncio.create_task(audio.submit_human_turn())
    await asyncio.sleep(0)

    assert not human.done()
    release_output.set()
    assert (await autonomous).stage is AudioStage.COMPLETED
    assert (await human).stage is AudioStage.COMPLETED


@pytest.mark.asyncio
async def test_failed_capture_to_output_transfer_does_not_call_tts() -> None:
    audio, coordinator, output = service(SpeechRecognitionEvent("hola", True))

    async def failed_transfer(_lease_id: str, _direction: AudioTurnDirection) -> bool:
        return False

    coordinator.transfer = failed_transfer  # type: ignore[method-assign]

    result = await audio.submit_human_turn()

    assert result.stage is AudioStage.TTS_FAILED
    assert output.spoken == []
    assert coordinator.is_free


@pytest.mark.asyncio
async def test_captures_once_and_passes_identical_audio_only_to_recognizer() -> None:
    metrics = AudioMetrics(4, 0, 16_000, 1, 2, 1_000, 1_000, False)
    captured = CapturedAudio(b"same-bytes", 16_000, 1, 2, 0, metrics)

    class Capture:
        calls = 0

        async def start(self) -> None:
            pass

        async def record(self) -> CapturedAudio:
            self.calls += 1
            return captured

        async def stop(self) -> None:
            pass

    class NoListen:
        async def listen(self, timeout: float | None = None) -> SpeechRecognitionEvent:
            raise AssertionError("AudioTurnService must not call listen")

    class Recognizer:
        received: bytes | None = None

        async def transcribe(self, audio: bytes, turn_id: str) -> SpeechRecognitionEvent:
            del turn_id
            self.received = audio
            return SpeechRecognitionEvent("hola", True)

    capture = Capture()
    recognizer = Recognizer()
    audio = AudioTurnService(
        capture_device="configured-capture",
        capture=capture,
        recognizer=recognizer,
        speech_input=NoListen(),
        speech_output=Output(completion()),
        coordinator=AudioTurnCoordinator(),
        respond=respond,
    )

    result = await audio.submit_human_turn()

    assert capture.calls == 1
    assert recognizer.received == b"same-bytes"
    assert result.turn_id
    assert result.diagnostics is metrics


@pytest.mark.asyncio
async def test_recognizer_receives_the_capture_bytes_and_turn_id() -> None:
    metrics = AudioMetrics(4, 0, 16_000, 1, 2, 1_000, 1_000, False)
    captured = CapturedAudio(b"captured-wav", 16_000, 1, 2, 0, metrics)

    class Capture:
        async def start(self) -> None:
            pass

        async def record(self) -> CapturedAudio:
            return captured

        async def stop(self) -> None:
            pass

    class Recognizer:
        received: tuple[bytes, str] | None = None

        async def transcribe(self, wav: bytes, turn_id: str) -> SpeechRecognitionEvent:
            self.received = (wav, turn_id)
            return SpeechRecognitionEvent("hola", True)

    recognizer = Recognizer()
    audio = AudioTurnService(
        capture_device="configured-capture",
        capture=Capture(),
        recognizer=recognizer,
        speech_output=Output(completion()),
        coordinator=AudioTurnCoordinator(),
        respond=respond,
    )

    result = await audio.submit_human_turn()

    assert recognizer.received == (b"captured-wav", result.turn_id)
    assert result.stage is AudioStage.COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metrics", "stage"),
    [
        (AudioMetrics(4, 0, 16_000, 1, 2, 0, 0, True), AudioStage.SILENCE),
        (AudioMetrics(4, 0, 16_000, 1, 2, 100, 100, False), AudioStage.SIGNAL_LOW),
    ],
)
async def test_capture_signal_terminal_stages_release_the_lease(
    metrics: AudioMetrics, stage: AudioStage
) -> None:
    class Capture:
        async def start(self) -> None:
            pass

        async def record(self) -> CapturedAudio:
            return CapturedAudio(b"wav", 16_000, 1, 2, 0, metrics)

        async def stop(self) -> None:
            pass

    coordinator = AudioTurnCoordinator()
    audio = AudioTurnService(
        capture_device="configured-capture",
        capture=Capture(),
        recognizer=Input(SpeechRecognitionEvent("hola", True)),
        speech_output=Output(completion()),
        coordinator=coordinator,
        respond=respond,
    )

    result = await audio.submit_human_turn()

    assert result.stage is stage
    assert coordinator.is_free


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "stage"),
    [
        (SpeechRecognitionError("decoder failed"), AudioStage.STT_FAILED),
        (SpeechRecognitionTimeoutError("decoder timed out"), AudioStage.STT_TIMEOUT),
    ],
)
async def test_recognizer_typed_failures_have_distinct_terminal_stages(
    failure: SpeechError, stage: AudioStage
) -> None:
    coordinator = AudioTurnCoordinator()
    audio = AudioTurnService(
        capture_device="configured-capture",
        recognizer=Input(failure),
        speech_output=Output(completion()),
        coordinator=coordinator,
        respond=respond,
    )

    result = await audio.submit_human_turn()

    assert result.stage is stage
    assert coordinator.is_free


@pytest.mark.asyncio
async def test_recognizer_load_failure_degrades_the_voice_turn_without_leaking_lease() -> None:
    class UnavailableRecognizer:
        async def start(self) -> None:
            raise SpeechRecognitionError("model failed")

        async def transcribe(self, wav: bytes, turn_id: str) -> SpeechRecognitionEvent:
            del wav, turn_id
            raise AssertionError("unavailable recognizer must not transcribe")

    coordinator = AudioTurnCoordinator()
    audio = AudioTurnService(
        capture_device="configured-capture",
        recognizer=UnavailableRecognizer(),
        speech_output=Output(completion()),
        coordinator=coordinator,
        respond=respond,
    )

    await audio.start()
    result = await audio.submit_human_turn()

    assert result.stage is AudioStage.STT_FAILED
    assert coordinator.is_free
