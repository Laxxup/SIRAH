"""Laboratory console client for the headless runtime."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from time import monotonic

from sirah.core.runtime_client import RuntimeClient
from sirah.core.runtime_transport import RuntimeTransportClient
from sirah.types import ClientKind

__all__ = ["LaboratoryConsole"]


class LaboratoryConsole:
    """Submit text and status requests without owning system resources."""

    def __init__(self, client: RuntimeClient) -> None:
        self._client = client
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            text = await self._read_input()
            if text is None:
                break
            await self._dispatch(text.strip())

    async def _read_input(self) -> str | None:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, lambda: input("\nTú > "))
        except (EOFError, KeyboardInterrupt):
            return None

    async def _dispatch(self, text: str) -> None:
        if not text:
            return
        if text == "/quit":
            self._running = False
            return
        if text == "/status":
            status = await self._client.read_status()
            print(f"Estado: {len(status.get('components', []))} componentes")
            return
        t0 = monotonic()
        result = await self._client.submit_text(text)
        message = result.get("message", {}).get("content", "")
        print(f"\nSIRAH ({(monotonic() - t0) * 1000:.0f}ms): {message}")


async def main() -> None:
    socket_path = Path(os.environ["SIRAH_RUNTIME_SOCKET"])
    secret = os.environ["SIRAH_CLI_SECRET"]
    client = RuntimeClient(
        ClientKind.CLI,
        RuntimeTransportClient(socket_path, ClientKind.CLI, secret),
    )
    await LaboratoryConsole(client).run()


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli()
