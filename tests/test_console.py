"""Laboratory console runtime-client tests."""

from __future__ import annotations

import pytest

from sirah.console import LaboratoryConsole
from sirah.core.runtime_client import RuntimeClient
from sirah.types import ClientKind, RuntimeRequest


class RecordingRuntime:
    def __init__(self) -> None:
        self.requests: list[RuntimeRequest] = []

    async def __call__(self, request: RuntimeRequest) -> object:
        self.requests.append(request)
        return {"message": {"content": "respuesta"}}


@pytest.mark.asyncio
async def test_console_dispatches_text_through_runtime_client(capsys) -> None:  # type: ignore[no-untyped-def]
    runtime = RecordingRuntime()
    console = LaboratoryConsole(
        client=RuntimeClient(ClientKind.CLI, runtime),
    )

    await console._dispatch("hola")

    assert runtime.requests[0].metadata == {"text": "hola"}
    assert "respuesta" in capsys.readouterr().out
