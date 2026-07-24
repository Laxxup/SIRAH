"""Comandos locales prioritarios y conservadores."""
from __future__ import annotations
from dataclasses import dataclass
from .capabilities import CapabilityRequest
from .cortex_integration import CapabilityExecutionResult, CapabilityRunner
from .errors import CapabilityRejectedError
from .speech import SpeechOutputPort

@dataclass(frozen=True, slots=True)
class StopResult:
    matched: bool
    tts_cancelled: bool
    robot_result: CapabilityExecutionResult | None
    reason: str

class LocalStopRouter:
    _STOP_WORDS = frozenset({"stop", "para", "detente", "detén"})
    def matches(self, text: str) -> bool:
        return text.strip().casefold().rstrip(".!?") in self._STOP_WORDS
    def route(self, text: str, *, speech: SpeechOutputPort, runner: CapabilityRunner, request_id: str) -> StopResult:
        if not self.matches(text):
            return StopResult(False, False, None, "not_local_stop")
        active = speech.active
        speech.stop()
        result = None
        try:
            result = runner.run(CapabilityRequest(request_id, "robot.stop"))
        except CapabilityRejectedError:
            pass
        return StopResult(True, active, result, "local_stop")
