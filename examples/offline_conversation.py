"""Demostración reproducible sin red ni SDK de Gemini."""

from sirah import (
    CapabilityRunner,
    ConversationOrchestrator,
    DecisionType,
    IntelligenceDecision,
    IntelligenceResponse,
    SessionContextStore,
    create_default_catalog,
)
from sirah.fake_intelligence import FakeIntelligenceAdapter
from sirah.simulated_robot import SimulatedRobotAdapter


def main() -> None:
    catalog = create_default_catalog()
    robot = SimulatedRobotAdapter()
    robot.connect()
    robot.read_events()
    fake = FakeIntelligenceAdapter(
        [
            IntelligenceResponse(
                IntelligenceDecision(
                    decision_type=DecisionType.REQUEST_CAPABILITY,
                    response_text="Solicitaré la posición inicial.",
                    capability="robot.home",
                ),
                provider="fake",
                model="scripted",
            )
        ]
    )
    orchestrator = ConversationOrchestrator(
        intelligence=fake,
        catalog=catalog,
        runner=CapabilityRunner(catalog, robot),
        contexts=SessionContextStore(),
    )
    result = orchestrator.handle("offline-demo", "ve a posición inicial")
    print(result.response_text)
    print(f"capability={result.requested_capability}")
    print(f"executed={result.capability_executed}")
    print(f"commands={[command.action for command in robot.commands]}")


if __name__ == "__main__":
    main()

