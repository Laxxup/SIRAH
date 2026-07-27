"""Smoke manual opt-in de PTT Vosk; no persiste audio."""

from __future__ import annotations

import os
import selectors
import sys
import time
from pathlib import Path

from sirah.audio_turn import AudioTurnCoordinator
from sirah.arecord_capture import ArecordPcmCapture, ArecordPcmConfig
from sirah.speech_input import SpeechInputRuntime, SpeechRecognitionEventKind
from sirah.vosk_recognizer import VoskRecognizerConfig, VoskSpeechRecognizer


def _positive_seconds(name: str, default: str) -> float:
    value = float(os.environ.get(name, default))
    if not 0 < value <= 120:
        raise ValueError
    return value


def main() -> int:
    if os.environ.get("SIRAH_RUN_VOSK_SMOKE") != "1":
        print("Precondición ausente: SIRAH_RUN_VOSK_SMOKE=1.")
        return 2
    model = os.environ.get("SIRAH_VOSK_MODEL")
    if not model or not sys.stdin.isatty():
        print("Precondición ausente: modelo externo y stdin TTY.")
        return 2
    try:
        duration = _positive_seconds("SIRAH_VOSK_SMOKE_MAX_SECONDS", "15")
        terminal_timeout = _positive_seconds(
            "SIRAH_VOSK_SMOKE_TERMINAL_SECONDS", "5"
        )
        capture = ArecordPcmCapture(
            ArecordPcmConfig(
                executable=os.environ.get("SIRAH_ARECORD_BIN", "arecord"),
                device=os.environ.get("SIRAH_AUDIO_INPUT_DEVICE"),
            )
        )
        recognizer = VoskSpeechRecognizer(VoskRecognizerConfig(Path(model)))
        runtime = SpeechInputRuntime(
            capture,
            recognizer,
            AudioTurnCoordinator(),
            maximum_duration_seconds=duration,
        )
    except (ValueError, OSError):
        print("Configuración inválida.")
        return 2
    if not runtime.available:
        print("Vosk, modelo o arecord no disponible.")
        runtime.close()
        return 2
    selector = selectors.DefaultSelector()
    selector.register(sys.stdin, selectors.EVENT_READ)
    try:
        print("Presiona Enter para comenzar")
        sys.stdin.readline()
        operation_id = runtime.start()
        print("Habla y presiona Enter para finalizar")
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            if selector.select(min(0.1, deadline - time.monotonic())):
                sys.stdin.readline()
                break
        runtime.finalize(operation_id)
        terminal_deadline = time.monotonic() + terminal_timeout
        while time.monotonic() < terminal_deadline:
            event = runtime.poll()
            if event is None:
                continue
            if event.kind is SpeechRecognitionEventKind.PARTIAL:
                continue
            length = len(event.text or "")
            print(f"Terminal: kind={event.kind.value}; chars={length}")
            if os.environ.get("SIRAH_VOSK_SMOKE_SHOW_TEXT") == "1" and event.text:
                print(event.text)
            return int(
                event.kind is not SpeechRecognitionEventKind.FINAL or length == 0
            )
        return 1
    except (KeyboardInterrupt, OSError):
        return 1
    finally:
        selector.close()
        runtime.close()
        assert runtime.state.value == "closed"
        assert not capture.active


if __name__ == "__main__":
    raise SystemExit(main())
