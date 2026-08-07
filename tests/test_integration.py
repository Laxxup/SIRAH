"""Integration tests through the headless runtime boundary."""

from __future__ import annotations

import pytest

from sirah.core.runtime import SirahRuntime
from sirah.types import ClientKind


@pytest.mark.asyncio
async def test_full_pipeline_conversation() -> None:
    runtime = SirahRuntime(client_secrets={ClientKind.CLI: "cli-secret"})

    await runtime.start()
    try:
        result = await runtime.submit_text("Hola, ¿cómo estás?")
        assert result.message.role == "assistant"
        assert "Hola" in result.message.content
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_full_pipeline_multiple_runtime_turns() -> None:
    runtime = SirahRuntime(client_secrets={ClientKind.CLI: "cli-secret"})

    await runtime.start()
    try:
        results = [await runtime.submit_text(text) for text in ("uno", "dos", "tres")]
        assert all(result.message.content for result in results)
        assert runtime.snapshot().healthy()
    finally:
        await runtime.stop()
