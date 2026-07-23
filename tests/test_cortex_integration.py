"""Integración real con Cortex y RobotPort simulado."""

import pytest

from sirah.capabilities import CapabilityPolicy, CapabilityRequest
from sirah.cortex_integration import CapabilityRunner, create_default_catalog
from sirah.errors import CapabilityRejectedError
from sirah.simulated_robot import SimulatedFailure, SimulatedRobotAdapter
from sirah_cortex import EventType, RobotPort


def connected_runner() -> tuple[CapabilityRunner, SimulatedRobotAdapter]:
    robot = SimulatedRobotAdapter()
    assert isinstance(robot, RobotPort)
    robot.connect()
    robot.read_events()
    return CapabilityRunner(create_default_catalog(), robot), robot


def test_required_capabilities_are_registered() -> None:
    names = {item.name for item in create_default_catalog().enabled()}
    assert {"robot.home", "robot.stop"} <= names


@pytest.mark.parametrize(
    ("capability", "action"), [("robot.home", "home"), ("robot.stop", "stop")]
)
def test_global_capabilities_reach_cortex_and_robot(
    capability: str, action: str
) -> None:
    runner, robot = connected_runner()
    result = runner.run(CapabilityRequest("req-1", capability))
    assert result.succeeded
    assert [command.action for command in robot.commands] == [action]
    assert [event.type for event in result.events] == [
        EventType.COMMAND_ACCEPTED,
        EventType.COMMAND_COMPLETED,
    ]


def test_greet_uses_cortex_provisional_plan_without_model_angles() -> None:
    runner, robot = connected_runner()
    result = runner.run(CapabilityRequest("req-greet", "arm.greet"))
    assert result.succeeded
    assert [command.action for command in robot.commands] == [
        "set_position",
        "set_position",
    ]
    assert [command.parameters["angle_deg"] for command in robot.commands] == [
        60.0,
        0.0,
    ]


def test_rejected_request_never_reaches_robot() -> None:
    runner, robot = connected_runner()
    with pytest.raises(CapabilityRejectedError):
        runner.run(CapabilityRequest("req-1", "robot.home", {"gpio": 4}))
    assert robot.commands == []


def test_disabled_request_never_reaches_robot() -> None:
    catalog = create_default_catalog(enable_greet=False)
    robot = SimulatedRobotAdapter()
    robot.connect()
    robot.read_events()
    with pytest.raises(CapabilityRejectedError):
        CapabilityRunner(catalog, robot).run(
            CapabilityRequest("req-1", "arm.greet")
        )
    assert robot.commands == []


def test_adapter_failure_is_observable() -> None:
    runner, robot = connected_runner()
    robot.next_failure = SimulatedFailure.REJECT
    result = runner.run(CapabilityRequest("req-1", "robot.home"))
    assert not result.succeeded
    assert result.delivered_commands == ()
    assert result.error and "RobotUnavailableError" in result.error
    assert [event.type for event in result.events] == [EventType.COMMAND_FAILED]


def test_order_is_observable() -> None:
    runner, robot = connected_runner()
    runner.run(CapabilityRequest("req-1", "robot.home"))
    runner.run(CapabilityRequest("req-2", "robot.stop"))
    assert [command.action for command in robot.commands] == ["home", "stop"]


def test_policy_can_be_used_without_runner() -> None:
    definition = CapabilityPolicy(create_default_catalog()).authorize(
        CapabilityRequest("req-1", "robot.home")
    )
    assert definition.name == "robot.home"

