"""SituationalCoordinator — composes perception, initiative, and speech."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from sirah.autonomy.idle_behavior import IdleBehavior
from sirah.autonomy.mood_engine import MoodEngine
from sirah.autonomy.person_tracker import PersonTracker
from sirah.core.orchestrator import SirahOrchestrator
from sirah.perception.port import PerceptionPort
from sirah.social.initiative import evaluate_initiative
from sirah.social.memory import InteractionMemory
from sirah.types import (
    InitiativeAction,
    InitiativeDecision,
)
from sirah.voice.audio_service import AudioTurnService

__all__ = ["SituationalCoordinator", "AutonomousCoordinator"]

logger = logging.getLogger(__name__)


class SituationalCoordinator:
    def __init__(
        self,
        orchestrator: SirahOrchestrator,
        perception: PerceptionPort | None = None,
        voice: AudioTurnService | None = None,
        interval_s: float = 0.5,
        silent: bool = False,
    ) -> None:
        self._orchestrator = orchestrator
        self._perception = perception
        self._voice = voice
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
            with suppress(asyncio.CancelledError):
                await self._task
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

        if self._voice is not None and decision.text:
            try:
                result = await self._voice.speak_autonomously(decision.text)
                if result.tts_completion is not None and result.tts_completion.success:
                    self._memory.record(f"greeted: {decision.text[:60]}")
            except Exception as exc:
                logger.error("Initiative speech failed: %s", exc)

    def mark_conversation_active(self, active: bool = True) -> None:
        self._conversation_active = active

    def set_voice_service(self, voice: AudioTurnService) -> None:
        self._voice = voice

    @property
    def memory(self) -> InteractionMemory:
        return self._memory


class AutonomousCoordinator:
    def __init__(
        self,
        orchestrator: SirahOrchestrator,
        perception: PerceptionPort | None = None,
        voice: AudioTurnService | None = None,
        interval_s: float = 0.5,
        silent: bool = False,
        enable_person_tracking: bool = True,
        enable_mood: bool = True,
        enable_idle: bool = True,
    ) -> None:
        self._orchestrator = orchestrator
        self._perception = perception
        self._voice = voice
        self._interval = interval_s
        self._silent = silent
        self._memory = InteractionMemory()
        self._conversation_active = False
        self._running = False
        self._task: asyncio.Task[object] | None = None

        self._person_tracker = PersonTracker() if enable_person_tracking else None
        self._mood = MoodEngine() if enable_mood else None
        self._idle = IdleBehavior() if enable_idle else None

    async def start(self) -> None:
        self._running = True
        if self._perception is not None:
            await self._perception.start()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("AutonomousCoordinator started (mood=%s, track=%s, idle=%s)",
                     self._mood is not None, self._person_tracker is not None, self._idle is not None)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._perception is not None:
            await self._perception.stop()
        logger.info("AutonomousCoordinator stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("AutonomousCoordinator error: %s", exc)
            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        if self._perception is None:
            return

        frame = await self._perception.capture()

        if self._mood is not None:
            events: list[str] = []
            if self._conversation_active:
                events.append("conversation_start")
            self._mood.update(tuple(events))

        decision = evaluate_initiative(frame, self._memory, self._conversation_active)

        if decision.action != InitiativeAction.SILENT:

            if self._person_tracker is not None and frame.faces:
                for face in frame.faces:
                    if face.landmarks:
                        dummy = PersonTracker.make_dummy_embedding(
                            hash(str(face.bbox))
                        )
                        known = self._person_tracker.identify_or_register(dummy)
                        if known.visit_count == 1:
                            decision = InitiativeDecision(
                                action=InitiativeAction.GREET,
                                text="¡Hola! Soy SIRAH. ¿Cómo te llamas?",
                                reason=f"new person: {known.name}",
                            )
                        elif known.relationship == "owner":
                            decision = InitiativeDecision(
                                action=InitiativeAction.CHECK_IN,
                                text="¡Hola de nuevo! ¿Todo bien?",
                                reason=f"owner returned (visit {known.visit_count})",
                            )

            if not self._silent and self._voice is not None and decision.text:
                logger.info("Autonomy initiative: %s", decision.reason)
                self._memory.mark_greet()
                try:
                    result = await self._voice.speak_autonomously(decision.text)
                    if result.tts_completion is not None and result.tts_completion.success:
                        self._memory.record(f"greeted: {decision.text[:60]}")
                        if self._mood is not None:
                            self._mood.update(("person_greeted",))
                except Exception as exc:
                    logger.error("Autonomy speech failed: %s", exc)

            return

        if self._idle is not None:
            idle_action = self._idle.tick()
            if idle_action is not None:
                action, text = idle_action
                logger.info("Idle: %s — %s", action.name, text)
                if not self._silent and self._voice is not None:
                    try:
                        await self._voice.speak_autonomously(text)
                    except Exception as exc:
                        logger.error("Idle speech failed: %s", exc)

    def mark_conversation_active(self, active: bool = True) -> None:
        self._conversation_active = active
        if self._idle is not None and active:
            self._idle.mark_active()

    def set_voice_service(self, voice: AudioTurnService) -> None:
        self._voice = voice

    @property
    def memory(self) -> InteractionMemory:
        return self._memory

    @property
    def person_tracker(self) -> PersonTracker | None:
        return self._person_tracker

    @property
    def mood(self) -> MoodEngine | None:
        return self._mood

    @property
    def idle(self) -> IdleBehavior | None:
        return self._idle
