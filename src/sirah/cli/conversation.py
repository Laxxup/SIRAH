"""Conversation CLI; real Cloud and audio actions require explicit --live."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from sirah.audio.capture import SoundDeviceAudioSource
from sirah.audio.contracts import Transcript
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


class _TextOnlyResponder:
    """Print validated model speech without initializing TTS or playback."""

    def __init__(self, proposer: OllamaIntentProposer) -> None:
        self._proposer = proposer

    async def respond(self, transcript) -> None:
        proposal = await self._proposer.propose(IntentRequest("speech_ended", transcript.text, transcript.ended_at))
        if proposal.speech:
            print(f"sirah> {proposal.speech}")

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
    listen.add_argument("--language", default=os.getenv("SIRAH_WHISPER_LANGUAGE", "es"))
    listen.add_argument("--ollama-model", default=os.getenv("SIRAH_OLLAMA_MODEL", "gpt-oss:20b-cloud"))
    listen.add_argument("--text-only", action="store_true", help="print replies; do not initialize Azure or audio output")
    listen.add_argument("--barge-in", action="store_true", help="experimental; acoustic echo cancellation is unavailable")
    listen.add_argument(
        "--tts-provider",
        choices=("local", "azure"),
        default=os.getenv("SIRAH_TTS_PROVIDER", "local"),
    )
    talk = commands.add_parser("push-to-talk", help="run real microphone capture only with --live")
    talk.add_argument("--live", action="store_true", help="acknowledge microphone and Cloud use")
    talk.add_argument("--input-device")
    talk.add_argument("--output-device")
    talk.add_argument("--sample-rate", type=int, default=16000)
    talk.add_argument("--duration", type=float)
    talk.add_argument("--whisper-model", default=os.getenv("SIRAH_WHISPER_MODEL", "base"))
    talk.add_argument("--language", default=os.getenv("SIRAH_WHISPER_LANGUAGE", "es"))
    talk.add_argument("--ollama-model", default=os.getenv("SIRAH_OLLAMA_MODEL", "gpt-oss:20b-cloud"))
    talk.add_argument("--text-only", action="store_true")
    chat = commands.add_parser("text-chat", help="real Cloud text chat; no microphone")
    chat.add_argument("--live", action="store_true")
    chat.add_argument("--ollama-model", default=os.getenv("SIRAH_OLLAMA_MODEL", "gpt-oss:20b-cloud"))
    chat.add_argument("--record-session", action="store_true")
    chat.add_argument("--include-text", action="store_true")
    tts = commands.add_parser("tts-check", help="check Azure TTS configuration")
    tts.add_argument("--live", action="store_true")
    tts.add_argument("--provider", choices=("local", "azure"), default=os.getenv("SIRAH_TTS_PROVIDER", "local"))
    tts.add_argument("--output-device")
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
    if not args.live:
        print(f"{args.command} is real microphone and Cloud mode; rerun with --live")
        return 2
    if args.command == "listen":
        try:
            return asyncio.run(_listen(args))
        except KeyboardInterrupt:
            return 0
    if args.command == "text-chat":
        if args.include_text and not args.record_session:
            parser.error("--include-text requires --record-session")
        return asyncio.run(_text_chat(args.ollama_model, args.record_session, args.include_text))
    if args.command == "tts-check":
        return asyncio.run(_tts_check(args.provider, args.output_device))
    print("Cloud transcripts may leave this device. Press Ctrl-C to stop after speaking.")
    return asyncio.run(_push_to_talk(args))


def _safe_config() -> dict[str, str]:
    return {key: ("configured" if any(word in key for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")) else value) for key, value in os.environ.items() if key.startswith("SIRAH_")}


def _ollama_configured() -> bool:
    return bool(os.getenv("SIRAH_OLLAMA_HOST") and os.getenv("SIRAH_OLLAMA_MODEL"))


def _device_id(value: str | None) -> int | str | None:
    return int(value) if value is not None and value.isdecimal() else value


def _logs(args: argparse.Namespace) -> int:
    from sirah.conversation.session_log import diagnose, resolve_session, session_files
    if args.logs_command == "list":
        for path in session_files():
            print(path.stem.split("_")[-1])
        return 0
    if args.logs_command == "purge":
        for path in session_files()[20:]:
            print(f"would delete {path.name}")
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
        print(f"would delete {path.name}")
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
        transcript = await FasterWhisperSTT(args.whisper_model, language=args.language).transcribe(chunks)
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
    config = ContinuousSessionConfig(
        threshold=float(os.getenv("SIRAH_VAD_THRESHOLD", "0.5")),
        min_speech_ms=int(os.getenv("SIRAH_VAD_MIN_SPEECH_MS", "250")),
        end_silence_ms=int(os.getenv("SIRAH_VAD_END_SILENCE_MS", "700")),
        max_turn_seconds=float(os.getenv("SIRAH_VAD_MAX_TURN_SECONDS", "15")),
        pre_roll_ms=int(os.getenv("SIRAH_VAD_PRE_ROLL_MS", "300")),
        barge_in=args.barge_in or os.getenv("SIRAH_BARGE_IN", "false").lower() == "true",
        post_playback_guard_ms=int(os.getenv("SIRAH_POST_PLAYBACK_GUARD_MS", "500")),
    )
    player: SoundDevicePCMPlayer | None = None
    conversation: ConversationSession | _TextOnlyResponder
    tts: OperationTTS
    if args.text_only:
        conversation = _TextOnlyResponder(_proposer(args.ollama_model))
    else:
        if args.tts_provider == "local":
            from sirah.audio.kokoro_tts import KokoroTextToSpeech

            print("preparando voz")
            local_tts = KokoroTextToSpeech.from_environment()
            await local_tts.synthesize("Hola.")
            tts, sample_rate = AsyncTTS(lambda: local_tts), local_tts.sample_rate
            print("listo")
        else:
            tts, sample_rate = _operation_tts(args.tts_provider)
        player = SoundDevicePCMPlayer(device=args.output_device, sample_rate=sample_rate)
        proposer = _proposer(args.ollama_model)
        conversation = ConversationSession(
            proposer,
            tts,
            player,
            core=ConversationCore(proposer),
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
        print(labels[state])

    async def show_error(error: Exception) -> None:
        print(f"error de sesion: {error}")

    session = ContinuousConversationSession(
        SoundDeviceAudioSource(
            sample_rate=args.sample_rate,
            blocksize=512 if args.sample_rate == 16_000 else 256,
            device=_device_id(args.input_device),
        ),
        SileroVoiceActivityDetector.from_official_distribution(threshold=config.threshold),
        FasterWhisperSTT(args.whisper_model, language=args.language),
        conversation,
        config=config,
        on_state_change=show_state,
        on_error=show_error,
    )
    print("escuchando; Ctrl-C para detener")
    if config.barge_in:
        print("El barge-in es experimental porque no existe cancelación de eco acústico.")
    try:
        await session.run()
    except KeyboardInterrupt:
        await session.stop()
    finally:
        if player is not None:
            await player.close()
    return 0


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
    from sirah.audio.azure_tts import AzureOperationTextToSpeech, AzureTextToSpeech

    return AzureOperationTextToSpeech(AzureTextToSpeech.from_environment()), 16_000


async def _tts_check(provider: str, output_device: str | None) -> int:
    if provider == "azure":
        from sirah.audio.azure_tts import AzureTextToSpeech

        try:
            AzureTextToSpeech.from_environment()
        except Exception as exc:  # noqa: BLE001
            print(f"Azure TTS unavailable: {type(exc).__name__}")
            return 1
        print("Azure TTS is configured; no synthesis was requested")
        return 0
    tts, sample_rate = _operation_tts("local")
    player = SoundDevicePCMPlayer(device=output_device, sample_rate=sample_rate)
    operation_id = "tts-check"
    phrase = "Hola, soy SIRAH. Mi voz local está funcionando."
    try:
        pcm = await tts.synthesize(operation_id, phrase)
        await player.play(operation_id, pcm)
        await player.join()
    except Exception as exc:  # noqa: BLE001
        print(f"Local TTS unavailable: {type(exc).__name__}: {exc}")
        return 1
    finally:
        await player.close()
    print(phrase)
    return 0
