"""SirahOrchestrator — main entry point that composes all layers."""

from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import TYPE_CHECKING, Protocol

from sirah.action.capabilities import CapabilityCatalog, CapabilityPolicy
from sirah.action.runner import ActionRunner
from sirah.autonomy.mood_engine import MoodEngine, MoodState
from sirah.core.context import ConversationContext
from sirah.core.registry import ComponentRegistry
from sirah.errors import (
    ActionError,
    IntelligenceError,
    PerceptionError,
)
from sirah.intelligence.port import IntelligencePort
from sirah.perception.port import PerceptionPort
from sirah.types import (
    CapabilityExecutionResult,
    ComponentId,
    ComponentKind,
    ComponentStatus,
    ConversationMessage,
    ConversationResult,
    DecisionType,
    IntelligenceDecision,
    IntelligenceRequest,
    PerceptionFrame,
    PresentContext,
    SpeechCompletion,
    SpeechRecognitionEvent,
    SystemSnapshot,
)
from sirah.voice.port import SpeechInputPort, SpeechOutputPort

if TYPE_CHECKING:
    from sirah.voice.audio_service import AudioTurnService

__all__ = ["SirahOrchestrator"]

logger = logging.getLogger(__name__)


class CortexRuntime(Protocol):
    """Minimal protocol for Cortex runtime bridge."""

    async def process_next(self) -> None: ...
    async def shutdown(self) -> None: ...


class SirahOrchestrator:
    def __init__(
        self,
        intelligence: IntelligencePort,
        perception: PerceptionPort | None,
        speech_input: SpeechInputPort | None,
        speech_output: SpeechOutputPort | None,
        capabilities: CapabilityCatalog,
        policy: CapabilityPolicy,
        action_runner: ActionRunner,
        cortex: CortexRuntime | None = None,
        context: ConversationContext | None = None,
        registry: ComponentRegistry | None = None,
        mood: MoodEngine | None = None,
    ) -> None:
        self._intelligence = intelligence
        self._perception = perception
        self._speech_input = speech_input
        self._speech_output = speech_output
        self._catalog = capabilities
        self._policy = policy
        self._runner = action_runner
        self._cortex = cortex
        self._context = context or ConversationContext()
        self._registry = registry or ComponentRegistry()
        self._mood = mood
        self._voice: AudioTurnService | None = None

        self._registry.register(ComponentKind.CORE, "orchestrator")
        self._registry.register(ComponentKind.INTELLIGENCE, "primary")
        self._registry.register(ComponentKind.PERCEPTION, "camera")
        self._registry.register(ComponentKind.VOICE, "speech")
        self._registry.register(ComponentKind.ACTION, "runner")

        self._running = False
        self._tasks: list[asyncio.Task[object]] = []

    @property
    def context(self) -> ConversationContext:
        return self._context

    @property
    def snapshot(self) -> SystemSnapshot:
        return self._registry.snapshot()

    @property
    def mood(self) -> MoodEngine | None:
        return self._mood

    def set_mood(self, state: MoodState) -> None:
        if self._mood is not None:
            self._mood._state = state

    async def start(self) -> None:
        self._running = True
        self._registry.update(
            ComponentId(ComponentKind.CORE, "orchestrator"),
            ComponentStatus.READY,
            "started",
        )
        self._registry.update(
            ComponentId(ComponentKind.INTELLIGENCE, "primary"),
            ComponentStatus.READY,
            "configured",
        )
        self._registry.update(
            ComponentId(ComponentKind.PERCEPTION, "camera"),
            ComponentStatus.READY,
            "configured",
        )
        self._registry.update(
            ComponentId(ComponentKind.VOICE, "speech"),
            ComponentStatus.READY,
            "configured",
        )
        self._registry.update(
            ComponentId(ComponentKind.ACTION, "runner"),
            ComponentStatus.READY,
            "configured",
        )
        logger.info("SirahOrchestrator started")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._registry.update(
            ComponentId(ComponentKind.CORE, "orchestrator"),
            ComponentStatus.SHUTDOWN,
            "stopped",
        )
        logger.info("SirahOrchestrator stopped")

    async def handle_text(self, user_text: str) -> ConversationResult:
        t0 = monotonic()
        self._context.present = PresentContext(user_text=user_text)
        self._context.add(
            ConversationMessage(role="user", content=user_text, timestamp=t0)
        )

        request = IntelligenceRequest(
            messages=self._context.messages,
            system_prompt_override=self._mood.system_prompt if self._mood else None,
        )
        try:
            response = await self._intelligence.decide(request)
            decision = response.decision
        except IntelligenceError:
            decision = IntelligenceDecision(
                decision_type=DecisionType.CONVERSATION,
                text_response="Lo siento, no puedo procesar eso ahora.",
            )
            self._registry.update(
                ComponentId(ComponentKind.INTELLIGENCE, "primary"),
                ComponentStatus.DEGRADED,
                "fallback response",
            )

        capability_result = None
        if decision is not None and decision.capability_name:
            capability_result = await self._execute_capability(decision)

        assistant_msg = ConversationMessage(
            role="assistant",
            content=decision.text_response if decision else "",
            timestamp=monotonic(),
        )
        self._context.add(assistant_msg)

        result = ConversationResult(
            message=assistant_msg,
            decision=decision,
            capability_result=capability_result,
        )
        self._registry.record_result(result)
        return result

    async def _execute_capability(
        self, decision: IntelligenceDecision
    ) -> CapabilityExecutionResult:
        from sirah.types import CapabilityRequest

        if decision.capability_name is None:
            return CapabilityExecutionResult(
                success=False,
                capability_name="unknown",
                error="no capability name",
            )

        request = CapabilityRequest(
            name=decision.capability_name,
            params=decision.capability_params,
        )
        try:
            authorised = self._policy.authorize(request)
            if not authorised:
                return CapabilityExecutionResult(
                    success=False,
                    capability_name=request.name,
                    error="policy denied",
                )
            return await self._runner.run(request)
        except ActionError as exc:
            return CapabilityExecutionResult(
                success=False,
                capability_name=request.name,
                error=str(exc),
            )

    async def say(self, text: str) -> SpeechCompletion:
        if self._voice is None:
            return SpeechCompletion(operation_id="noop", success=False, error="no TTS")
        result = await self._voice.speak_autonomously(text)
        return result.tts_completion or SpeechCompletion(
            operation_id=result.turn_id, success=False, error=result.stage.value
        )

    def set_voice_service(self, voice: AudioTurnService) -> None:
        self._voice = voice

    async def listen(self, timeout: float = 10.0) -> SpeechRecognitionEvent:
        del timeout
        return SpeechRecognitionEvent(text="", is_final=False, confidence=0.0)

    async def perceive(self) -> PerceptionFrame:
        if self._perception is None:
            return PerceptionFrame(timestamp=monotonic())
        try:
            return await self._perception.capture()
        except PerceptionError:
            return PerceptionFrame(timestamp=monotonic())

    async def run_loop(self) -> None:
        """Continuous perception → thought → speech loop."""
        while self._running:
            frame = await self.perceive()
            self._registry.record_result(
                ConversationResult(
                    message=ConversationMessage(
                        role="system",
                        content=f"Faces: {len(frame.faces)}",
                        timestamp=monotonic(),
                    )
                )
            )
            await asyncio.sleep(0.1)

    @property
    def is_running(self) -> bool:
        return self._running
