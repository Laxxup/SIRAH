"""Pruebas de componentes y snapshot del presente operativo."""

from sirah import (
    CapabilityRunner,
    SessionContextStore,
    create_default_catalog,
)
from sirah.simulated_robot import SimulatedRobotAdapter
from sirah.system import (
    ComponentId,
    ComponentKind,
    ComponentRegistry,
    ComponentState,
    ComponentStatus,
    PresentSystem,
)


def system(*, greet: bool = False) -> tuple[PresentSystem, SimulatedRobotAdapter]:
    robot = SimulatedRobotAdapter()
    robot.connect()
    robot.read_events()
    catalog = create_default_catalog(enable_greet=greet)
    registry = ComponentRegistry(
        [
            ComponentState(
                ComponentId("robot.simulated"),
                ComponentKind.ROBOT,
                ComponentStatus.SIMULATED,
                True,
                "RobotPort local.",
            )
        ]
    )
    context = SessionContextStore()
    return (
        PresentSystem(
            components=registry,
            catalog=catalog,
            contexts=context,
            robot=robot,
            intelligence_provider="fake-laboratory",
        ),
        robot,
    )


def test_registry_is_extensible_and_rejects_duplicates() -> None:
    registry = ComponentRegistry()
    component = ComponentState(
        ComponentId("input.microphone"),
        ComponentKind.INPUT,
        ComponentStatus.UNAVAILABLE,
        False,
        "No configurado.",
    )
    registry.register(component)
    assert registry.get("input.microphone") is component


def test_snapshot_contains_safe_operational_state() -> None:
    present, _ = system(greet=True)
    snapshot = present.snapshot("session")
    assert snapshot.intelligence_provider == "fake-laboratory"
    assert set(snapshot.enabled_capabilities) == {
        "robot.home",
        "robot.stop",
        "arm.greet",
    }
    assert snapshot.recent_message_count == 0
    assert all("KEY" not in repr(component) for component in snapshot.components)


def test_snapshot_reflects_last_capability_and_observations() -> None:
    present, robot = system()
    result = CapabilityRunner(present.catalog, robot).run(
        __import__("sirah").CapabilityRequest("request-1", "robot.home")
    )
    present.contexts.update_action(
        "session", capability="robot.home", result="succeeded"
    )
    present.record_result(
        type(
            "Result",
            (),
            {
                "requested_capability": "robot.home",
                "mechanical_result": result,
                "safe_error": None,
            },
        )()
    )
    snapshot = present.snapshot("session")
    assert snapshot.last_capability == "robot.home"
    assert snapshot.last_result == "succeeded"
    assert snapshot.recent_commands == ("home",)
    assert "command.completed" in snapshot.recent_events


def test_snapshot_does_not_include_private_messages() -> None:
    present, _ = system()
    present.contexts.append(
        "session",
        __import__("sirah").ConversationMessage("user", "mensaje privado"),
    )
    snapshot = present.snapshot("session")
    assert not hasattr(snapshot, "messages")
    assert snapshot.recent_message_count == 1
