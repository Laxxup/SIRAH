"""LocalStopRouter — exact match for stop commands."""

from __future__ import annotations

from typing import Protocol

__all__ = ["LocalStopRouter"]

STOP_PATTERNS = ("stop", "para", "detente", "alto", "basta", "quieto", "pausa")


class _StopRunner(Protocol):
    async def stop_all(self) -> None: ...


class LocalStopRouter:
    def matches(self, text: str) -> bool:
        cleaned = text.strip().lower()
        return cleaned in STOP_PATTERNS

    def dispatch(self, runner: _StopRunner) -> bool:
        import asyncio

        async def _stop() -> bool:
            await runner.stop_all()
            return True

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(_stop())
