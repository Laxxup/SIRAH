"""Conversation CLI; real Cloud and audio actions require explicit --live.

This module is the CLI boundary: argument parsing, `main` and the offline
diagnostic commands (devices, replay, config, logs, Ollama probes,
tts-check). The live modes live in `conversation_modes` and provider
selection in `conversation_providers`; the names below are re-exported so
`sirah-conversation` and existing tests keep working unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from sirah.audio.playback import SoundDevicePCMPlayer
from sirah.audio.replay import load_replay
from sirah.cli.conversation_modes import (
    _build_vision_pipeline,
    _capture_metrics,
    _listen,
    _push_to_talk,
    _show_lab_diagnostic,
    _text_chat,
    _TextOnlyResponder,
    _vision_chat,
)
from sirah.cli.conversation_providers import (
    _device_id,
    _ollama_configured,
    _operation_stt,
    _operation_tts,
    _proposer,
)
from sirah.conversation.contracts import IntentRequest
from sirah.conversation.timing import TurnTiming

__all__ = [
    "_TextOnlyResponder",
    "_build_vision_pipeline",
    "_capture_metrics",
    "_device_id",
    "_listen",
    "_logs",
    "_ollama_configured",
    "_ollama_diagnostic",
    "_ollama_stream_probe",
    "_operation_stt",
    "_operation_tts",
    "_proposer",
    "_push_to_talk",
    "_safe_config",
    "_show_lab_diagnostic",
    "_text_chat",
    "_tts_check",
    "_vision_chat",
    "build_parser",
    "main",
]


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