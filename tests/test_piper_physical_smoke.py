"""Explicit physical Piper smoke; excluded unless an operator opts in."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sirah.voice.tts_piper import AplayPlayer, PiperTTS


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("SIRAH_RUN_PIPER_PHYSICAL_SMOKE") != "1",
    reason="set SIRAH_RUN_PIPER_PHYSICAL_SMOKE=1 for real local audio",
)
async def test_piper_physical_smoke() -> None:
    """Load the server-provided voice and play a short fixed Spanish phrase."""
    output = PiperTTS(
        model_path=Path(os.environ["SIRAH_RUNTIME_PIPER_MODEL"]),
        config_path=Path(os.environ["SIRAH_RUNTIME_PIPER_CONFIG"]),
        player=AplayPlayer(os.environ["SIRAH_RUNTIME_OUTPUT_DEVICE"]),
    )
    await output.start()
    try:
        completion = await output.speak("Prueba de voz de SIRAH.")
    finally:
        await output.stop()

    assert completion.success
