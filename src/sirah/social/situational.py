"""SituationalCoordinator — composes perception, initiative, and speech."""

from __future__ import annotations

import asyncio
import logging
from time import monotonic

from sirah.core.orchestrator import SirahOrchestrator
from sirah.perception.port import PerceptionPort
from sirah.voice.port import SpeechOutputPort
from sirah.social.memory import InteractionMemory
from sirah.social.initiative import evaluate_initiative
from sirah.types import (
    InitiativeDecision,
    InitiativeAction,
    ComponentKind,
    ComponentStatus,
    ComponentId,
)

__all__ = ["SituationalCoordinator"]

logger = logging.getLogger(__name__)


class SituationalCoordinator:
    def __init__(
        self,
        orchestrator: SirahOrchestrator,
        perception: PerceptionPort | None = None,
        speech: SpeechOutputPort | None = None,
        interval_s: float = 0.5,
        silent: bool = False,
    ) -> None:
        self._orchestrator = orchestrator
        self._perception = perception
        self._speech = speech
        self._interval = interval_s
        self._silent = silent
        self._memory = InteractionMemory()
        self._running = False
        self._task: asyncio.Task[object] | None = None
        self._conversation_active = False

    async def start(self) -> None:
        self._running = True
        if self._perception is not None:
            await self._perception.start()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("SituationalCoordinator started (silent=%s)", self._silent)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._perception is not None:
            await self._perception.stop()
        logger.info("SituationalCoordinator stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("SituationalCoordinator error: %s", exc)
            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        if self._perception is None:
            return

        frame = await self._perception.capture()
        decision = evaluate_initiative(frame, self._memory, self._conversation_active)

        if decision.action == InitiativeAction.SILENT:
            return

        if self._silent:
            logger.debug("Initiative suppressed (silent mode): %s", decision.reason)
            return

        logger.info("Initiative: %s — %s", decision.action.value, decision.reason)

        self._memory.mark_greet()

        if self._speech is not None and decision.text:
            try:
                completion = await self._speech.speak(decision.text)
                if completion.success:
                    self._memory.record(f"greeted: {decision.text[:60]}")
            except Exception as exc:
                logger.error("Initiative speech failed: %s", exc)

    def mark_conversation_active(self, active: bool = True) -> None:
        self._conversation_active = active

    @property
    def memory(self) -> InteractionMemory:
        return self._memory
