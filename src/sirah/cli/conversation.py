"""Conversation CLI; real Cloud and audio actions require explicit --live."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections.abc import Awaitable
from pathlib import Path
from typing import Protocol

from sirah.audio.capture import SoundDeviceAudioSource
from sirah.audio.contracts import Transcript
from sirah.audio.groq_stt import GroqWhisperSTT
from sirah.audio.playback import SoundDevicePCMPlayer
from sirah.audio.replay import load_replay
from sirah.audio.stt import FasterWhisperSTT
from sirah.audio.tts import AsyncTTS
from sirah.audio.vad import SileroVoiceActivityDetector
from sirah.conversation.continuous import (
    ContinuousConversationSession,
    ContinuousSessionConfig,
    ConversationState,
)
from sirah.conversation.contracts import IntentRequest
from sirah.conversation.core import ConversationCore
from sirah.conversation.ollama import OllamaIntentProposer
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sirah-conversation")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("devices", help="list real audio devices when audio support is installed")
    replay = commands.add_parser("replay", help="inspect an offline audio replay; never opens hardware")
    replay.add_argument("path", type=Path)
    check = commands.add_parser("ollama-check", help="check Cloud configuration without sending text")
    check.add_argument("--live", action="store_true", help="permit one diagnostic request")
    stream_probe = commands.add_parser(
        "ollama-stream-probe", help="measure Ollama stream timing without saving assistant text"
    )
    stream_probe.add_argument("--live", action="store_true", help="permit one diagnostic request")
    stream_probe.add_argument("--prompt", default="Responde solo: Hola.")
    stream_probe.add_argument("--context-limit", type=int, default=0)
    stream_probe.add_argument("--think", choices=("default", "false", "low"), default="default")
    commands.add_parser("config", help="show effective configuration with secrets redacted")
    logs = commands.add_parser("logs", help="inspect explicitly recorded SIRAH session logs")
    log_commands = logs.add_subparsers(dest="logs_command", required=True)
    log_commands.add_parser("list")
    for name in ("latest", "show", "diagnose", "delete"):
        command = log_commands.add_parser(name)
        if name not in ("latest",):
            command.add_argument("session_id", nargs="?", default="latest")
    log_commands.add_parser("purge")
    listen = commands.add_parser("listen", help="hands-free local VAD conversation; requires --live")
    listen.add_argument("--live", action="store_true", help="acknowledge microphone and Cloud use")
    listen.add_argument("--input-device")
    listen.add_argument("--output-device")
    listen.add_argument("--sample-rate", type=int, default=16000)
    listen.add_argument("--whisper-model", default=os.getenv("SIRAH_WHISPER_MODEL", "base"))
    listen.add_argument("--stt-provider", choices=("local", "groq"), default=os.getenv("SIRAH_STT_PROVIDER", "local"))
    listen.add_argument("--language", default=os.getenv("SIRAH_WHISPER_LANGUAGE", "es"))
    listen.add_argument("--ollama-model", default=os.getenv("SIRAH_OLLAMA_MODEL", "gpt-oss:20b-cloud"))
    listen.add_argument("--text-only", action="store_true", help="print replies; do not initialize Azure or audio output")
    listen.add_argument("--barge-in", action="store_true", help="experimental; acoustic echo cancellation is unavailable")
    listen.add_argument("--lab", action="store_true", help="show states and metrics without saving content")
    listen.add_argument("--show-text", action="store_true", help="show recognized text; terminal scrollback may retain it")
    listen.add_argument("--record-session", action="store_true")
    listen.add_argument("--include-text", action="store_true")
    listen.add_argument(
        "--tts-provider",
        choices=("local", "azure", "edge"),
        default=os.getenv("SIRAH_TTS_PROVIDER", "local"),
    )
    listen.add_argument(
        "--camera-device",
        default=None,
        help="enable live vision for voice turns; requires --yunet-model",
    )
    listen.add_argument(
        "--yunet-model",
        default=None,
        help="local verified YuNet face model (.onnx); enables vision with --camera-device",
    )
    listen.add_argument(
        "--gesture-model",
        default=None,
        help="optional local verified MediaPipe gesture model (gesture_recognizer.task)",
    )
    listen.add_argument(
        "--person-model",
        default=None,
        help="optional local verified MediaPipe person model (efficientdet_lite0.tflite)",
    )
    listen.add_argument(
        "--log-gesture-telemetry",
        action="store_true",
        help="print one diagnostic line per gesture evidence feed (opt-in; "
        "never logs landmarks or frames)",
    )
    listen.add_argument(
        "--log-vision-context",
        action="store_true",
        help="print the exact vision block injected into each per-turn "
        "LLM request (opt-in, per turn, never per frame)",
    )
    talk = commands.add_parser("push-to-talk", help="run real microphone capture only with --live")
    talk.add_argument("--live", action="store_true", help="acknowledge microphone and Cloud use")
    talk.add_argument("--input-device")
    talk.add_argument("--output-device")
    talk.add_argument("--sample-rate", type=int, default=16000)
    talk.add_argument("--duration", type=float)
    talk.add_argument("--whisper-model", default=os.getenv("SIRAH_WHISPER_MODEL", "base"))
    talk.add_argument("--stt-provider", choices=("local", "groq"), default=os.getenv("SIRAH_STT_PROVIDER", "local"))
    talk.add_argument("--language", default=os.getenv("SIRAH_WHISPER_LANGUAGE", "es"))
    talk.add_argument("--ollama-model", default=os.getenv("SIRAH_OLLAMA_MODEL", "gpt-oss:20b-cloud"))
    talk.add_argument("--text-only", action="store_true")
    chat = commands.add_parser("text-chat", help="real Cloud text chat; no microphone")
    chat.add_argument("--live", action="store_true")
    chat.add_argument("--ollama-model", default=os.getenv("SIRAH_OLLAMA_MODEL", "gpt-oss:20b-cloud"))
    chat.add_argument("--record-session", action="store_true")
    chat.add_argument("--include-text", action="store_true")
    vision_chat = commands.add_parser(
        "vision-chat",
        help="real Cloud text chat grounded on live vision (YuNet + optional "
        "gesture and person models); requires --live",
    )
    vision_chat.add_argument("--live", action="store_true")
    vision_chat.add_argument("--camera-device", required=True)
    vision_chat.add_argument("--yunet-model", required=True)
    vision_chat.add_argument(
        "--gesture-model",
        default=None,
        help="local verified MediaPipe gesture model (gesture_recognizer.task)",
    )
    vision_chat.add_argument(
        "--person-model",
        default=None,
        help="local verified MediaPipe person model (efficientdet_lite0.tflite)",
    )
    vision_chat.add_argument(
        "--ollama-model", default=os.getenv("SIRAH_OLLAMA_MODEL", "gpt-oss:20b-cloud")
    )
    vision_chat.add_argument(
        "--log-gesture-telemetry",
        action="store_true",
        help="print one diagnostic line per gesture evidence feed (latency, "
        "frame age, allowlisted gestures, candidate X/samples, events); "
        "never logs landmarks or frames",
    )
    vision_chat.add_argument(
        "--log-vision-context",
        action="store_true",
        help="print the exact vision block injected into each per-turn "
        "LLM request (opt-in, per turn, never per frame); no images, "
        "landmarks, boxes or payloads",
    )
    tts = commands.add_parser("tts-check", help="check Azure TTS configuration")
    tts.add_argument("--live", action="store_true")
    tts.add_argument("--provider", choices=("local", "azure", "edge"), default=os.getenv("SIRAH_TTS_PROVIDER", "local"))
    tts.add_argument("--output-device")
    tts.add_argument("--text", default="Hola, soy SIRAH. Mi voz está funcionando.")
    tts.add_argument("--lab", action="store_true", help="show latency timings without saving text or audio")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "devices":
        try:
            import sounddevice
        except (ImportError, OSError) as exc:
            print(f"audio support unavailable: {exc}")
            return 1
        print(sounddevice.query_devices())
        return 0
    if args.command == "replay":
        replay = load_replay(args.path)
        print(json.dumps({"mode": "offline", "chunks": len(replay.chunks), "transcripts": len(replay.transcripts)}))
        return 0
    if args.command == "config":
        print(json.dumps(_safe_config(), sort_keys=True))
        return 0
    if args.command == "logs":
        return _logs(args)
    if args.command == "ollama-check":
        if not args.live:
            print(json.dumps({"configured": _ollama_configured(), "live": False}))
            return 0
        return asyncio.run(_ollama_diagnostic())
    if args.command == "ollama-stream-probe":
        if not args.live:
            print(json.dumps({"configured": _ollama_configured(), "live": False}))
            return 0
        return asyncio.run(_ollama_stream_probe(args.prompt, args.context_limit, args.think))
    if not args.live:
        print(f"{args.command} is real microphone and Cloud mode; rerun with --live")
        return 2
    if args.command == "listen":
        if args.show_text and not args.lab:
            parser.error("--show-text requires --lab")
        if args.include_text and not args.record_session:
            parser.error("--include-text requires --record-session")
        if (args.camera_device is None) != (args.yunet_model is None):
            parser.error("--camera-device and --yunet-model must be provided together to enable vision")
        try:
            return asyncio.run(_listen(args))
        except KeyboardInterrupt:
            return 0
    if args.command == "text-chat":
        if args.include_text and not args.record_session:
            parser.error("--include-text requires --record-session")
        return asyncio.run(_text_chat(args.ollama_model, args.record_session, args.include_text))
    if args.command == "vision-chat":
        try:
            return asyncio.run(_vision_chat(args))
        except KeyboardInterrupt:
            return 0
    if args.command == "tts-check":
        return asyncio.run(_tts_check(args.provider, args.output_device, args.text, lab=args.lab))
    print("Cloud transcripts may leave this device. Press Ctrl-C to stop after speaking.")
    try:
        return asyncio.run(_push_to_talk(args))
    except KeyboardInterrupt:
        return 0


def _safe_config() -> dict[str, str]:
    return {key: ("configured" if any(word in key for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")) else value) for key, value in os.environ.items() if key.startswith("SIRAH_")}


def _ollama_configured() -> bool:
    return bool(os.getenv("SIRAH_OLLAMA_HOST") and os.getenv("SIRAH_OLLAMA_MODEL"))


def _device_id(value: str | None) -> int | str | None:
    return int(value) if value is not None and value.isdecimal() else value


def _logs(args: argparse.Namespace) -> int:
    from sirah.conversation.session_log import (
        delete_session,
        diagnose,
        purge_sessions,
        resolve_session,
        session_files,
    )
    if args.logs_command == "list":
        for path in session_files():
            print(path.stem.split("_")[-1])
        return 0
    if args.logs_command == "purge":
        for path in purge_sessions():
            print(f"deleted {path.name}")
        return 0
    try:
        path = resolve_session(getattr(args, "session_id", "latest"))
    except FileNotFoundError as exc:
        print(str(exc))
        return 1
    if args.logs_command == "latest":
        print(path.stem.split("_")[-1])
    elif args.logs_command == "show":
        print(path.read_text(encoding="utf-8"), end="")
    elif args.logs_command == "diagnose":
        print(json.dumps(diagnose(path), ensure_ascii=False))
    else:
        delete_session(getattr(args, "session_id", "latest"))
        print(f"deleted {path.name}")
    return 0


async def _ollama_diagnostic() -> int:
    if not _ollama_configured():
        print("Ollama is not configured; no request was sent")
        return 1
    started = time.monotonic()
    try:
        proposal = await _proposer().propose(IntentRequest("diagnostic", "Responde JSON con Hola", 0.0))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"success": False, "error": type(exc).__name__}))
        return 1
    print(json.dumps({"success": True, "intent": proposal.intent.value, "latency_s": round(time.monotonic() - started, 3)}))
    return 0


async def _ollama_stream_probe(prompt: str, context_limit: int, think: str) -> int:
    from sirah.conversation.ollama import OllamaStreamProbe

    if not _ollama_configured():
        print("Ollama is not configured; no request was sent")
        return 1
    try:
        metrics = await OllamaStreamProbe.from_environment().measure(
            prompt,
            context_limit=context_limit,
            think={"default": None, "false": False, "low": "low"}[think],
        )
    except Exception as exc:  # noqa: BLE001 - provider errors are reported without content.
        print(json.dumps({"success": False, "error": type(exc).__name__}))
        return 1
    print(
        json.dumps(
            {
                "success": True,
                "request_bytes": metrics.request_bytes,
                "context_items": metrics.context_items,
                "events": metrics.events,
                "content_events": metrics.content_events,
                "thinking_events": metrics.thinking_events,
                "first_event_ms": metrics.first_event_ms,
                "first_content_ms": metrics.first_content_ms,
                "total_ms": metrics.total_ms,
                "prompt_tokens": metrics.prompt_tokens,
                "output_tokens": metrics.output_tokens,
            }
        )
    )
    return 0


def _proposer(model: str | None = None) -> OllamaIntentProposer:
    env = dict(os.environ)
    if model:
        env["SIRAH_OLLAMA_MODEL"] = model
    return OllamaIntentProposer.from_environment(environ=env)


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


def _operation_tts(provider: str) -> tuple[OperationTTS, int]:
    if provider == "local":
        from sirah.audio.kokoro_tts import KokoroTextToSpeech

        return AsyncTTS(KokoroTextToSpeech.from_environment), KokoroTextToSpeech.sample_rate
    if provider == "edge":
        from sirah.audio.edge_tts import EdgeTextToSpeech
        from sirah.audio.kokoro_tts import KokoroTextToSpeech
        from sirah.audio.tts import FallbackTTS

        # Edge is a network provider; fall back to the local Kokoro voice at
        # the same sample rate (24 kHz) when the cloud is unreachable.
        return (
            FallbackTTS(
                EdgeTextToSpeech.from_environment,
                KokoroTextToSpeech.from_environment,
                on_fallback=lambda exc: print(f"edge TTS falló; usando voz local: {type(exc).__name__}"),
            ),
            EdgeTextToSpeech.sample_rate,
        )
    from sirah.audio.azure_tts import AzureOperationTextToSpeech, AzureTextToSpeech

    return AzureOperationTextToSpeech(AzureTextToSpeech.from_environment()), 16_000


def _capture_metrics(dropped_chunks: int, queue_high_water_mark: int) -> str:
    if dropped_chunks == 0:
        return f"captura: sin descartes; cola max {queue_high_water_mark}/8"
    return f"captura: {dropped_chunks} frames descartados; cola max {queue_high_water_mark}/8"


def _show_lab_diagnostic(message: str) -> None:
    print(f"diagnóstico: {message}")


def _operation_stt(provider: str, model: str, language: str):
    if provider == "groq":
        return GroqWhisperSTT.from_environment()
    return FasterWhisperSTT(model, language=language)


async def _tts_check(
    provider: str,
    output_device: str | None,
    text: str = "Hola, soy SIRAH. Mi voz está funcionando.",
    *,
    lab: bool = False,
) -> int:
    if provider == "azure":
        from sirah.audio.azure_tts import AzureTextToSpeech

        try:
            AzureTextToSpeech.from_environment()
        except Exception as exc:  # noqa: BLE001
            print(f"Azure TTS unavailable: {type(exc).__name__}")
            return 1
        print("Azure TTS is configured; no synthesis was requested")
        return 0
    tts, sample_rate = _operation_tts(provider)
    player = SoundDevicePCMPlayer(device=output_device, sample_rate=sample_rate)
    operation_id = "tts-check"
    timing = TurnTiming() if lab else None
    try:
        if timing is not None:
            timing.mark(f"TTS {provider}: iniciando")
        stream = getattr(tts, "stream", None)
        play_stream = getattr(player, "play_stream", None)
        if stream is not None and play_stream is not None:
            first_chunk = True

            async def observed_stream():
                nonlocal first_chunk
                async for pcm in stream(operation_id, text):
                    if first_chunk and timing is not None:
                        first_chunk = False
                        timing.mark(f"TTS {provider}: primer PCM listo")
                        timing.mark("Altavoz: iniciando")
                    yield pcm

            await play_stream(operation_id, observed_stream())
        else:
            pcm = await tts.synthesize(operation_id, text)
            if timing is not None:
                timing.mark(f"TTS {provider}: PCM listo")
                timing.mark("Altavoz: iniciando")
            await player.play(operation_id, pcm)
            await player.join()
        if timing is not None:
            timing.mark("Altavoz: reproducción terminada")
    except Exception as exc:  # noqa: BLE001
        print(f"{provider} TTS unavailable: {type(exc).__name__}: {exc}")
        return 1
    finally:
        await player.close()
    print(text)
    return 0
