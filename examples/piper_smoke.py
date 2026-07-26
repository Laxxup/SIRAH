"""Smoke opt-in de Piper y reproducción local; no descarga modelos."""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path

from sirah.piper_speech import PiperSpeechConfig, PiperSpeechOutput
from sirah.speech import SpeechOutcome


def main() -> int:
    if os.environ.get("SIRAH_RUN_PIPER_SMOKE") != "1":
        print("SKIP: requiere SIRAH_RUN_PIPER_SMOKE=1.")
        return 2
    required = {
        name: os.environ.get(name)
        for name in (
            "SIRAH_PIPER_BIN",
            "SIRAH_PIPER_MODEL",
            "SIRAH_AUDIO_PLAYER",
        )
    }
    if not all(required.values()):
        print("ERROR: configuración Piper explícita incompleta.")
        return 2
    temporary_directory = Path(tempfile.mkdtemp(prefix="sirah-piper-smoke-"))
    temporary_directory.chmod(0o700)
    adapter = PiperSpeechOutput(
        PiperSpeechConfig(
            piper_executable=required["SIRAH_PIPER_BIN"] or "",
            model_path=Path(required["SIRAH_PIPER_MODEL"] or ""),
            player_argv=(required["SIRAH_AUDIO_PLAYER"] or "",),
            temporary_directory=temporary_directory,
            synthesis_timeout_seconds=30.0,
            playback_timeout_seconds=30.0,
            termination_grace_seconds=1.0,
        )
    )
    try:
        if not adapter.available:
            print(f"UNAVAILABLE: {adapter.unavailable_reason}")
            return 2
        operation_id = adapter.start("Hola.")
        deadline = time.monotonic() + 65.0
        completion = None
        waiter = threading.Event()
        while completion is None and time.monotonic() < deadline:
            completion = adapter.poll()
            if completion is None:
                waiter.wait(0.05)
        if completion is None:
            adapter.stop(operation_id)
            print("TIMEOUT: smoke total.")
            return 1
        print(f"TERMINAL: {completion.outcome.value}; {completion.safe_reason}")
        return 0 if completion.outcome is SpeechOutcome.COMPLETED else 1
    finally:
        adapter.close()
        if tuple(temporary_directory.glob("*.wav")):
            print("ERROR: quedó un WAV temporal.")


if __name__ == "__main__":
    raise SystemExit(main())
