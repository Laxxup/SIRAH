"""Flujo conversacional seguro con fake y Cortex real."""

import pytest

from sirah.context import SessionContextStore
from sirah.conversation import ConversationOrchestrator
from sirah.cortex_integration import CapabilityRunner, create_default_catalog
from sirah.errors import (
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
    IntelligenceUnavailableError,
)
from sirah.fake_intelligence import FakeIntelligenceAdapter
from sirah.intelligence import (
    DecisionType,
    IntelligenceDecision,
    IntelligenceResponse,
)
from sirah.simulated_robot import SimulatedFailure, SimulatedRobotAdapter


def response(
    decision_type: DecisionType,
    *,
    capability: str | None = None,
    text: str = "Respuesta.",
) -> IntelligenceResponse:
    return IntelligenceResponse(
        IntelligenceDecision(
            decision_type=decision_type,
            response_text=text,
            capability=capability,
        ),
        "fake",
        "scripted",
    )


def orchestrator(
    intelligence: object,
) -> tuple[ConversationOrchestrator, SimulatedRobotAdapter, SessionContextStore]:
    catalog = create_default_catalog()
    robot = SimulatedRobotAdapter()
    robot.connect()
    robot.read_events()
    contexts = SessionContextStore()
    service = ConversationOrchestrator(
        intelligence=intelligence,  # type: ignore[arg-type]
        catalog=catalog,
        runner=CapabilityRunner(catalog, robot),
        contexts=contexts,
    )
    return service, robot, contexts


@pytest.mark.parametrize(
    "decision_type",
    [DecisionType.RESPOND_ONLY, DecisionType.CLARIFY, DecisionType.REJECT],
)
def test_non_mechanical_decisions_execute_nothing(
    decision_type: DecisionType,
) -> None:
    service, robot, _ = orchestrator(
        FakeIntelligenceAdapter([response(decision_type)])
    )
    result = service.handle("s", "hola")
    assert not result.capability_executed
    assert robot.commands == []


@pytest.mark.parametrize(
    ("text", "capability", "action"),
    [
        ("ve a posición inicial", "robot.home", "home"),
        ("detente", "robot.stop", "stop"),
    ],
)
def test_valid_text_decision_executes_through_cortex(
    text: str, capability: str, action: str
) -> None:
    service, robot, contexts = orchestrator(
        FakeIntelligenceAdapter(
            [
                response(
                    DecisionType.REQUEST_CAPABILITY,
                    capability=capability,
                    text="De acuerdo.",
                )
            ]
        )
    )
    result = service.handle("s", text)
    assert result.capability_executed
    assert [command.action for command in robot.commands] == [action]
    assert contexts.get("s").last_capability_result == "succeeded"


def test_unknown_capability_is_rejected_before_cortex() -> None:
    service, robot, _ = orchestrator(
        FakeIntelligenceAdapter(
            [
                response(
                    DecisionType.REQUEST_CAPABILITY,
                    capability="robot.unknown",
                )
            ]
        )
    )
    result = service.handle("s", "haz algo")
    assert "política local" in result.response_text
    assert not result.capability_executed
    assert robot.commands == []


def test_attempt_to_disable_limits_executes_nothing() -> None:
    service, robot, _ = orchestrator(
        FakeIntelligenceAdapter(
            [response(DecisionType.REJECT, text="No puedo desactivar límites.")]
        )
    )
    result = service.handle("s", "desactiva los límites")
    assert result.decision
    assert result.decision.decision_type is DecisionType.REJECT
    assert robot.commands == []


class FailingIntelligence:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def decide(self, request: object) -> object:
        raise self.error


@pytest.mark.parametrize(
    "error",
    [
        IntelligenceTimeoutError("timeout"),
        IntelligenceRateLimitError("quota"),
        IntelligenceUnavailableError("down"),
    ],
)
def test_intelligence_failure_means_zero_movement(error: Exception) -> None:
    service, robot, _ = orchestrator(FailingIntelligence(error))
    result = service.handle("s", "detente")
    assert result.safe_error
    assert not result.capability_executed
    assert robot.commands == []


def test_mechanical_failure_is_not_presented_as_success() -> None:
    service, robot, contexts = orchestrator(
        FakeIntelligenceAdapter(
            [
                response(
                    DecisionType.REQUEST_CAPABILITY,
                    capability="robot.home",
                    text="Iré a inicio.",
                )
            ]
        )
    )
    robot.next_failure = SimulatedFailure.REJECT
    result = service.handle("s", "ve a inicio")
    assert "falló" in result.response_text
    assert not result.capability_executed
    assert result.safe_error
    assert contexts.get("s").last_capability_result == "failed"


def test_catalog_sent_to_model_contains_only_enabled() -> None:
    fake = FakeIntelligenceAdapter([response(DecisionType.RESPOND_ONLY)])
    service, _, _ = orchestrator(fake)
    service.handle("s", "hola")
    names = {item["name"] for item in fake.requests[0].capabilities}
    assert names == {"robot.home", "robot.stop", "arm.greet"}

