"""Entrega terminales STT a stop local o conversación, nunca desde el worker."""

from __future__ import annotations

from dataclasses import dataclass

from .conversation import ConversationOrchestrator, ConversationResult
from .local_commands import LocalStopRouter, StopResult
from .speech import SpeechOutputPort
from .speech_input import (
    SpeechInputRuntime,
    SpeechRecognitionEvent,
    SpeechRecognitionEventKind,
)
from .cortex_integration import CapabilityRunner


@dataclass(frozen=True, slots=True)
class SpeechInputDispatch:
    event: SpeechRecognitionEvent
    stop: StopResult | None = None
    conversation: ConversationResult | None = None


class SpeechInputCoordinator:
    def __init__(
        self,
        speech_input: SpeechInputRuntime,
        *,
        stop_router: LocalStopRouter,
        speech_output: SpeechOutputPort,
        runner: CapabilityRunner,
        conversation: ConversationOrchestrator,
        session_id: str,
    ) -> None:
        self.input = speech_input
        self._stop_router = stop_router
        self._output = speech_output
        self._runner = runner
        self._conversation = conversation
        self._session_id = session_id
        self._operation_id: str | None = None

    def start(self) -> str:
        operation_id = self.input.start()
        self._operation_id = operation_id
        return operation_id

    def poll(self) -> SpeechInputDispatch | None:
        event = self.input.poll()
        if event is None:
            return None
        if event.kind is SpeechRecognitionEventKind.PARTIAL:
            return SpeechInputDispatch(event)
        if event.operation_id != self._operation_id:
            return SpeechInputDispatch(event)
        self._operation_id = None
        if event.kind is not SpeechRecognitionEventKind.FINAL:
            return SpeechInputDispatch(event)
        text = (event.text or "").strip()
        if self._stop_router.matches(text):
            stop = self._stop_router.route(
                text,
                speech=self._output,
                runner=self._runner,
                request_id=f"{self._session_id}:speech-stop",
            )
            return SpeechInputDispatch(event, stop=stop)
        return SpeechInputDispatch(
            event,
            conversation=self._conversation.handle(self._session_id, text),
        )
