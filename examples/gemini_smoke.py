"""Smoke test Gemini opt-in, siempre con RobotPort simulado."""

import os
import sys

from sirah import (
    CapabilityRunner,
    ConversationOrchestrator,
    SessionContextStore,
    create_default_catalog,
)
from sirah.errors import IntelligenceError
from sirah.gemini import GeminiIntelligenceAdapter
from sirah.simulated_robot import SimulatedRobotAdapter


def main() -> int:
    if os.environ.get("SIRAH_RUN_LIVE_GEMINI") != "1":
        print("Omitido: define SIRAH_RUN_LIVE_GEMINI=1 para habilitarlo.")
        return 2
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        print("Omitido: falta GEMINI_API_KEY o GOOGLE_API_KEY.")
        return 2
    catalog = create_default_catalog(enable_greet=False)
    robot = SimulatedRobotAdapter()
    robot.connect()
    robot.read_events()
    try:
        orchestrator = ConversationOrchestrator(
            intelligence=GeminiIntelligenceAdapter(max_retries=1),
            catalog=catalog,
            runner=CapabilityRunner(catalog, robot),
            contexts=SessionContextStore(),
        )
        result = orchestrator.handle("live-smoke", "Responde sin mover el robot.")
    except IntelligenceError as error:
        print(f"Gemini no disponible: {type(error).__name__}")
        return 1
    decision = result.decision.decision_type.value if result.decision else "error"
    print(f"decision={decision}")
    print(f"capability={result.requested_capability}")
    print(f"authorized={result.capability_executed}")
    print(f"commands={len(robot.commands)}")
    if result.safe_error:
        print(f"safe_error={result.safe_error.split(':', 1)[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
