"""Ejecución de capacidades autorizadas mediante SIRAH Cortex."""

from __future__ import annotations

from dataclasses import dataclass

from sirah_cortex import (
    ActionExecutor,
    Event,
    RobotCommand,
    RobotPort,
    SafetySupervisor,
    SirahError,
)
from sirah_cortex.domain.behavior import (
    BehaviorDecision,
    BehaviorIntent,
    BehaviorPriority,
)
from sirah_cortex.services.action_planner import plan_actions

from .capabilities import (
    CapabilityCatalog,
    CapabilityDefinition,
    CapabilityPolicy,
    CapabilityRequest,
)
from .errors import CapabilityExecutionError


@dataclass(frozen=True, slots=True)
class CapabilityExecutionResult:
    """Resultado observable sin afirmar movimiento físico no confirmado."""

    request: CapabilityRequest
    succeeded: bool
    delivered_commands: tuple[RobotCommand, ...]
    events: tuple[Event, ...]
    error: str | None = None


def _global_command(
    request: CapabilityRequest, action: str
) -> tuple[RobotCommand, ...]:
    return (
        RobotCommand(
            action=action,
            target="",
            command_id=f"{request.request_id}:0",
        ),
    )


def _home(request: CapabilityRequest) -> tuple[RobotCommand, ...]:
    return _global_command(request, "home")


def _stop(request: CapabilityRequest) -> tuple[RobotCommand, ...]:
    return _global_command(request, "stop")


def _greet(request: CapabilityRequest) -> tuple[RobotCommand, ...]:
    """Delega la mecánica de saludo a la planificación provisional de Cortex."""

    plan = plan_actions(
        BehaviorDecision(
            intent=BehaviorIntent.GREET_PERSON,
            reason=f"Capacidad SIRAH autorizada: {request.request_id}",
            priority=BehaviorPriority.NORMAL,
            source_state_version=0,
        )
    )
    return plan.commands


def create_default_catalog(*, enable_greet: bool = True) -> CapabilityCatalog:
    """Registra únicamente capacidades con traducción real comprobada."""

    catalog = CapabilityCatalog()
    for name, description, translator, enabled in (
        (
            "robot.home",
            "Solicita la posición inicial global del robot.",
            _home,
            True,
        ),
        (
            "robot.stop",
            "Solicita detener de forma normal la actividad.",
            _stop,
            True,
        ),
        (
            "arm.greet",
            "Ejecuta el saludo determinista definido por Cortex.",
            _greet,
            enable_greet,
        ),
    ):
        catalog.register(
            CapabilityDefinition(
                name=name,
                description=description,
                parameters={},
                enabled=enabled,
                translator=translator,
            )
        )
    return catalog


class CapabilityRunner:
    """Autoriza, traduce y entrega una capacidad una sola vez."""

    def __init__(
        self,
        catalog: CapabilityCatalog,
        robot: RobotPort,
        safety: SafetySupervisor | None = None,
    ) -> None:
        self._policy = CapabilityPolicy(catalog)
        self._robot = robot
        self._executor = ActionExecutor(robot, safety or SafetySupervisor())

    def run(self, request: CapabilityRequest) -> CapabilityExecutionResult:
        definition = self._policy.authorize(request)
        commands = definition.translator(request)
        delivered: list[RobotCommand] = []
        try:
            for command in commands:
                delivered.append(self._executor.execute(command))
        except SirahError as error:
            return CapabilityExecutionResult(
                request=request,
                succeeded=False,
                delivered_commands=tuple(delivered),
                events=tuple(self._robot.read_events()),
                error=f"{type(error).__name__}: {error}",
            )
        except Exception as error:
            raise CapabilityExecutionError(
                "Fallo inesperado durante la ejecución de la capacidad."
            ) from error
        return CapabilityExecutionResult(
            request=request,
            succeeded=True,
            delivered_commands=tuple(delivered),
            events=tuple(self._robot.read_events()),
        )

