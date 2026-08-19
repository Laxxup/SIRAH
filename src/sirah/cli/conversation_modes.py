"""Live conversation modes and vision glue for the `sirah-conversation` CLI.

`_listen`, `_push_to_talk`, `_text_chat` and `_vision_chat` are the real
microphone/Cloud modes reached only with `--live`. `_build_vision_pipeline`
and the observers glue live vision into the conversation; the output helpers
(`_capture_metrics`, `_show_lab_diagnostic`) also live here so the hub never
imports them back. Provider selection stays in `conversation_providers`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections.abc import Awaitable
from pathlib import Path
from typing import Protocol

from sirah.audio.capture import SoundDeviceAudioSource
from sirah.audio.contracts import Transcript
from sirah.audio.playback import SoundDevicePCMPlayer
from sirah.audio.stt import FasterWhisperSTT
from sirah.audio.tts import AsyncTTS
from sirah.audio.vad import SileroVoiceActivityDetector
from sirah.cli.conversation_providers import (
    _device_id,
    _ollama_configured,
    _operation_stt,
    _operation_tts,
    _proposer,
)
from sirah.conversation.continuous import (
    ContinuousConversationSession,
    ContinuousSessionConfig,
    ConversationState,
)
from sirah.conversation.contracts import IntentRequest
from sirah.conversation.core import ConversationCore
from sirah.conversation.session import ConversationSession, OperationTTS
from sirah.conversation.timing import TurnTiming


class _TextOnlyResponder:
    """Print validated model speech without initializing TTS or playback."""

    def __init__(self, core: ConversationCore, *, show_text: bool = False, log=None) -> None:
        self._core = core
        self._show_text = show_text
        self._log = log

    async def respond(self, transcript) -> None:
        proposal = await self._core.respond(transcript)
        if self._show_text:
            print(f"tú> {transcript.text} (confianza {transcript.confidence:.2f})")
        if proposal.speech:
            print(f"sirah> {proposal.speech}")
        if self._log is not None:
            self._log.write("response_validated", transcript=transcript.text, validated_speech=proposal.speech, intent=proposal.intent.value, stt_confidence=transcript.confidence)

    async def interrupt(self) -> None:
        return None


def _gesture_telemetry_logger(telemetry) -> None:
    """Print one gesture evidence feed for physical latency diagnosis."""
    pending = ", ".join(
        f"{p.value} {p.confirm_count}/{p.confirm_samples}" for p in telemetry.pending
    )
    age = f"{telemetry.frame_age_ms:.1f}ms" if telemetry.frame_age_ms is not None else "n/a"
    print(
        f"[gesture t={telemetry.monotonic_s:.3f}s "
        f"infer={telemetry.inference_latency_ms:.1f}ms "
        f"age={age} "
        f"raw={telemetry.raw_gestures} "
        f"pending={pending or '-'} "
        f"stable={telemetry.stable or '-'} "
        f"events={telemetry.events or '-'}]"
    )


def _vision_context_logger(vision_block: str | None) -> None:
    """Print the EXACT vision block injected into one LLM turn.

    Called by `ConversationCore` just before the request is sent; the
    block is the same string the request carries (the core passes the
    value it computed, the logger never re-reads vision). `None` means
    the turn had no visual grounding.
    """
    print(f"[vision-context t={time.monotonic():.3f}s]")
    if vision_block:
        print(vision_block)
    else:
        print("(visión no disponible: sin grounding visual)")
    print("[/vision-context]")


class _VisionSurface(Protocol):
    """The part of `VisionPipeline` a CLI mode needs (lazy-import safe)."""

    def start(self) -> Awaitable[None]: ...
    def stop(self) -> Awaitable[None]: ...
    def vision_context(self) -> str | None: ...


def _build_vision_pipeline(args: argparse.Namespace) -> _VisionSurface | None:
    """Build (do NOT start) the shared VisionPipeline from CLI args.

    Returns None when vision is not requested, so the ordinary voice flow
    keeps working without a camera. Face grounding requires BOTH
    --camera-device and --yunet-model; --gesture-model/--person-model are
    optional extras. Every mode reuses the same VisionPipeline/Evidence/
    WorldState provider — nothing here duplicates perception or
    conversation logic.
    """
    camera_device = getattr(args, "camera_device", None)
    yunet_model = getattr(args, "yunet_model", None)
    if not camera_device or not yunet_model:
        return None
    from sirah.perception.mediapipe_gesture import MediaPipeGestureRecognizer
    from sirah.perception.mediapipe_person import MediaPipePersonDetector
    from sirah.perception.opencv_camera import OpenCVCameraSource
    from sirah.perception.vision_pipeline import VisionPipeline
    from sirah.perception.yunet import YuNetFaceDetector

    camera = OpenCVCameraSource(camera_device)
    detector = YuNetFaceDetector(Path(yunet_model))
    gesture_recognizer = (
        MediaPipeGestureRecognizer(Path(args.gesture_model))
        if args.gesture_model
        else None
    )
    person_detector = (
        MediaPipePersonDetector(Path(args.person_model))
        if args.person_model
        else None
    )
    observer = (
        _gesture_telemetry_logger
        if getattr(args, "log_gesture_telemetry", False)
        else None
    )
    return VisionPipeline(
        camera=camera,
        face_detector=detector,
        gesture_recognizer=gesture_recognizer,
        person_detector=person_detector,
        gesture_observer=observer,
    )


async def _push_to_talk(args: argparse.Namespace) -> int:
    if not _ollama_configured():
        print("Ollama is not configured; no audio was captured")
        return 1
    source = SoundDeviceAudioSource(sample_rate=args.sample_rate, device=args.input_device)
    await source.start()
    try:
        if args.duration is None:
            await asyncio.to_thread(input, "Press Enter to start recording, then Enter again to stop. ")
            stop_task = asyncio.create_task(asyncio.to_thread(input, "Recording. Press Enter to stop. "))
            stop_at = None
        else:
            stop_at = time.monotonic() + args.duration
            stop_task = None
        chunks = []
        while (stop_task is not None and not stop_task.done()) or (stop_at is not None and time.monotonic() < stop_at):
            chunks.append(await asyncio.wait_for(source.next_chunk(), timeout=1.0))
        if stop_task is not None:
            await stop_task
        transcript = await _operation_stt(args.stt_provider, args.whisper_model, args.language).transcribe(chunks)
        print(f"transcript: {transcript.text}")
        if args.text_only:
            proposal = await _proposer(args.ollama_model).propose(IntentRequest("speech_ended", transcript.text, transcript.ended_at))
            print(f"speech: {proposal.speech or ''}")
        return 0
    finally:
        await source.stop()


async def _listen(args: argparse.Namespace) -> int:
    if not _ollama_configured():
        print("Ollama is not configured; no audio was captured")
        return 1
    # Vision is opt-in: the ordinary voice flow must keep working without a
    # camera. The pipeline is built (not started) here so its provider can
    # feed the same ConversationCore; it starts only when the voice session
    # is about to run, and perception then runs on its OWN tasks ahead of
    # the conversation — never waiting for STT/Ollama/TTS.
    pipeline = _build_vision_pipeline(args)
    vision_context = pipeline.vision_context if pipeline is not None else None
    vision_logger = _vision_context_logger if args.log_vision_context else None
    config = ContinuousSessionConfig(
        threshold=float(os.getenv("SIRAH_VAD_THRESHOLD", "0.5")),
        min_speech_ms=int(os.getenv("SIRAH_VAD_MIN_SPEECH_MS", "250")),
        end_silence_ms=int(os.getenv("SIRAH_VAD_END_SILENCE_MS", "700")),
        max_turn_seconds=float(os.getenv("SIRAH_VAD_MAX_TURN_SECONDS", "15")),
        pre_roll_ms=int(os.getenv("SIRAH_VAD_PRE_ROLL_MS", "300")),
        barge_in=args.barge_in or os.getenv("SIRAH_BARGE_IN", "false").lower() == "true",
        post_playback_guard_ms=int(os.getenv("SIRAH_POST_PLAYBACK_GUARD_MS", "500")),
    )
    log = None
    if args.record_session:
        from sirah.conversation.session_log import SessionLog
        if args.include_text:
            print("Esta sesión guardará transcripciones y respuestas para diagnóstico. No se guardará audio.")
        log = SessionLog(include_text=args.include_text)
    player: SoundDevicePCMPlayer | None = None
    conversation: ConversationSession | _TextOnlyResponder
    tts: OperationTTS
    timing = TurnTiming() if args.lab else None
    if args.text_only:
        proposer = _proposer(args.ollama_model)
        conversation = _TextOnlyResponder(
            ConversationCore(
                proposer,
                vision_context=vision_context,
                vision_logger=vision_logger,
            ),
            show_text=args.show_text,
            log=log,
        )
    else:
        if args.tts_provider == "local":
            from sirah.audio.kokoro_tts import KokoroTextToSpeech

            print("preparando voz")
            local_tts = KokoroTextToSpeech.from_environment()
            await local_tts.preload()
            tts, sample_rate = AsyncTTS(lambda: local_tts), local_tts.sample_rate
            print("listo")
        else:
            tts, sample_rate = _operation_tts(args.tts_provider)
        player = SoundDevicePCMPlayer(device=args.output_device, sample_rate=sample_rate)
        proposer = _proposer(args.ollama_model)

        async def observe_response(transcript, proposal) -> None:
            if args.show_text:
                print(f"tú> {transcript.text} (confianza {transcript.confidence:.2f})")
                print(f"sirah> {proposal.speech or ''}")
            if log is not None:
                log.write("response_validated", transcript=transcript.text, validated_speech=proposal.speech, intent=proposal.intent.value, emotion=proposal.emotion.value, stt_confidence=transcript.confidence)

        conversation = ConversationSession(
            proposer,
            tts,
            player,
            core=ConversationCore(
                proposer,
                vision_context=vision_context,
                vision_logger=vision_logger,
            ),
            on_response=observe_response,
            on_diagnostic=_show_lab_diagnostic if args.lab else None,
            timing=timing,
        )

    async def show_state(state: ConversationState) -> None:
        labels = {
            ConversationState.IDLE: "listo",
            ConversationState.LISTENING: "escuchando",
            ConversationState.PROCESSING: "procesando",
            ConversationState.SPEAKING: "hablando",
            ConversationState.INTERRUPTING: "interrumpido",
            ConversationState.RECOVERING: "recuperandose",
            ConversationState.STOPPED: "detenido",
        }
        if args.lab or state is not ConversationState.IDLE:
            print(labels[state])

    async def show_error(error: Exception) -> None:
        print(f"error de sesion: {error}")

    async def on_state_changed(state: ConversationState) -> None:
        await show_state(state)

    stt = _operation_stt(args.stt_provider, args.whisper_model, args.language)
    if isinstance(stt, FasterWhisperSTT):
        print("preparando reconocimiento")
        await stt.preload()
        print("listo")
    source = SoundDeviceAudioSource(
        sample_rate=args.sample_rate,
        blocksize=512 if args.sample_rate == 16_000 else 256,
        device=_device_id(args.input_device),
    )
    session = ContinuousConversationSession(
        source,
        SileroVoiceActivityDetector.from_official_distribution(threshold=config.threshold),
        stt,
        conversation,
        config=config,
        on_state_change=on_state_changed,
        on_error=show_error,
        timing=timing,
        stt_label="STT Groq" if args.stt_provider == "groq" else "STT local",
    )
    print("escuchando; Ctrl-C para detener")
    if config.barge_in:
        print("El barge-in es experimental porque no existe cancelación de eco acústico.")
    if pipeline is not None:
        await pipeline.start()
        print("visión en vivo lista")
    try:
        await session.run()
    except KeyboardInterrupt:
        await session.stop()
    finally:
        if log is not None:
            log.close()
        if player is not None:
            await player.close()
        if pipeline is not None:
            await pipeline.stop()
        if args.lab:
            print(_capture_metrics(source.dropped_chunks, source.queue_high_water_mark))
    return 0


def _capture_metrics(dropped_chunks: int, queue_high_water_mark: int) -> str:
    if dropped_chunks == 0:
        return f"captura: sin descartes; cola max {queue_high_water_mark}/8"
    return f"captura: {dropped_chunks} frames descartados; cola max {queue_high_water_mark}/8"


def _show_lab_diagnostic(message: str) -> None:
    print(f"diagnóstico: {message}")


async def _vision_chat(args: argparse.Namespace) -> int:
    """Cloud text chat grounded on live vision: camera → workers → evidence
    → WorldState → compact AI context → the normal LLM path."""
    if not _ollama_configured():
        print("Ollama is not configured; no vision chat was started")
        return 1
    pipeline = _build_vision_pipeline(args)
    if pipeline is None:
        print("visión no configurada: se requieren --camera-device y --yunet-model")
        return 1
    await pipeline.start()
    print("visión en vivo lista; Ctrl-C para detener")
    try:
        vision_logger = _vision_context_logger if args.log_vision_context else None
        core = ConversationCore(
            _proposer(args.ollama_model),
            vision_context=pipeline.vision_context,
            vision_logger=vision_logger,
        )
        while True:
            text = await asyncio.to_thread(input, "you> ")
            if not text.strip():
                return 0
            observed_at = time.monotonic()
            proposal = await core.respond(Transcript(text, observed_at, observed_at, 1.0))
            print(f"sirah> {proposal.speech or ''}")
    finally:
        await pipeline.stop()


async def _text_chat(model: str, record_session: bool = False, include_text: bool = False) -> int:
    core = ConversationCore(_proposer(model))
    log = None
    if record_session:
        from sirah.conversation.session_log import SessionLog
        if include_text:
            print("Esta sesión guardará transcripciones y respuestas para diagnóstico. No se guardará audio.")
        log = SessionLog(include_text=include_text)
    while True:
        text = await asyncio.to_thread(input, "you> ")
        if not text.strip():
            if log is not None:
                log.close()
            return 0
        observed_at = time.monotonic()
        proposal = await core.respond(Transcript(text, observed_at, observed_at, 1.0))
        if log is not None:
            log.write("response_validated", turn_id=len(core._context), transcript=text, validated_speech=proposal.speech, intent=proposal.intent.value, emotion=proposal.emotion.value)
        print(f"sirah> {proposal.speech or ''}")