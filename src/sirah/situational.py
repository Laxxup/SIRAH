"""Fachada fina del circuito situacional; la lógica vive en módulos especializados."""
from .interaction import InitiativeAction, InitiativeDecision, InteractionMemory, evaluate_initiative
from .local_commands import LocalStopRouter, StopResult
from .simulation import FakeClock, MonotonicClock, FakeSpeechOutput, SimulatedPerception
from .situational_runtime import SituationalCoordinator, SituationalError, build_situational_runtime
__all__ = ["FakeClock", "FakeSpeechOutput", "InitiativeAction", "InitiativeDecision", "InteractionMemory", "LocalStopRouter", "MonotonicClock", "SimulatedPerception", "SituationalCoordinator", "SituationalError", "StopResult", "build_situational_runtime", "evaluate_initiative"]
