"""Piper failures must update the runtime-owned voice component."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from sirah.core.devices import DeviceRegistry
from sirah.core.runtime import SirahRuntime
from sirah.types import ClientKind, ComponentId, ComponentKind, ComponentStatus


@pytest.mark.asyncio
async def test_runtime_marks_voice_degraded_when_piper_fails_after_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sirah.voice.tts_piper as piper_module

    failure_callback: Callable[[], None] | None = None

    class FailingPiper:
        def __init__(self, **kwargs: object) -> None:
            nonlocal failure_callback
            failure_callback = cast(Callable[[], None], kwargs["on_failure"])

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def health(self) -> bool:
            return False

        async def speak(self, text: str) -> object:
            del text
            assert failure_callback is not None
            failure_callback()
            raise RuntimeError("Piper failed")

    monkeypatch.setattr(piper_module, "PiperTTS", FailingPiper)
    (tmp_path / "voice.onnx").write_bytes(b"fake")
    (tmp_path / "voice.onnx.json").write_text("{}")
    runtime = SirahRuntime(
        socket_path=tmp_path / "sirah.sock",
        client_secrets={ClientKind.CLI: "cli-secret"},
        devices=DeviceRegistry(output_devices=("default",)),
        piper_model_path=tmp_path / "voice.onnx",
        piper_config_path=tmp_path / "voice.onnx.json",
        tts="piper",
    )

    await runtime.start()
    try:
        await runtime._audio.speak_autonomously("hola")  # type: ignore[union-attr]
        assert runtime._assembly.registry.component_status(  # type: ignore[union-attr]
            ComponentId(ComponentKind.VOICE, "speech")
        ) is ComponentStatus.DEGRADED
    finally:
        await runtime.stop()
