"""Registro de componentes y representación segura del presente operativo."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from sirah_cortex import RobotPort

from .capabilities import CapabilityCatalog
from .context import PresentContext, SessionContextStore
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interaction import InteractionMemory


class ComponentKind(str, Enum):
    INTELLIGENCE = "intelligence"
    CONTEXT = "context"
    CONTROL = "control"
    ROBOT = "robot"
    BODY = "body"
    PERCEPTION = "perception"
    INPUT = "input"
    OUTPUT = "output"
    MEMORY = "memory"


class ComponentStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    SIMULATED = "simulated"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class ComponentId:
    """Identificador estable de un componente."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or "." not in self.value:
            raise ValueError("ComponentId debe ser un nombre estable con dominio.")


@dataclass(frozen=True, slots=True)
class ComponentState:
    """Estado seguro, descriptivo y sin objetos de implementación."""

    identifier: ComponentId
    kind: ComponentKind
    status: ComponentStatus
    simulated: bool
    description: str
    capabilities: tuple[str, ...] = ()
    last_error: str | None = None


class ComponentRegistry:
    """Registro extensible sin acoplar componentes futuros al núcleo."""

    def __init__(self, components: Iterable[ComponentState] = ()) -> None:
        self._components: dict[str, ComponentState] = {}
        for component in components:
            self.register(component)

    def register(self, component: ComponentState) -> None:
        key = component.identifier.value
        if key in self._components:
            raise ValueError(f"Componente duplicado: {key}")
        self._components[key] = component

    def replace(self, component: ComponentState) -> None:
        self._components[component.identifier.value] = component

    def all(self) -> tuple[ComponentState, ...]:
        return tuple(self._components.values())

    def get(self, identifier: str) -> ComponentState | None:
        return self._components.get(identifier)


@dataclass(frozen=True, slots=True)
class SystemSnapshot:
    """Instantánea de lectura del presente, no una base de datos."""

    session_id: str
    intelligence_provider: str
    components: tuple[ComponentState, ...]
    enabled_capabilities: tuple[str, ...]
    safety_state: str
    last_capability: str | None
    last_result: str | None
    recent_message_count: int
    robot_connected: bool
    recent_commands: tuple[str, ...]
    recent_events: tuple[str, ...]
    safe_errors: tuple[str, ...]
    silent_mode: bool = False
    autonomy_active: bool = True
    tts_active: bool = False
    last_initiative_reason: str | None = None


class PresentSystem:
    """Forma snapshots combinando contratos existentes de SIRAH."""

    def __init__(
        self,
        *,
        components: ComponentRegistry,
        catalog: CapabilityCatalog,
        contexts: SessionContextStore,
        robot: RobotPort,
        intelligence_provider: str,
    ) -> None:
        self.components = components
        self.catalog = catalog
        self.contexts = contexts
        self.robot = robot
        self.intelligence_provider = intelligence_provider
        self._recent_commands: list[str] = []
        self._recent_events: list[str] = []
        self._safe_errors: list[str] = []
        self._interaction_memory: InteractionMemory | None = None

    def record_result(self, result: object) -> None:
        """Registra solo campos resumidos de un ConversationResult."""

        capability = getattr(result, "requested_capability", None)
        mechanical = getattr(result, "mechanical_result", None)
        if capability:
            self._recent_commands.extend(
                command.action for command in getattr(mechanical, "delivered_commands", ())
            )
            self._recent_events.extend(
                event.type.value for event in getattr(mechanical, "events", ())
            )
        error = getattr(result, "safe_error", None)
        if error:
            self._safe_errors.append(str(error).split(":", 1)[0])
        self._recent_commands = self._recent_commands[-8:]
        self._recent_events = self._recent_events[-8:]
        self._safe_errors = self._safe_errors[-4:]

    def record_interaction_state(self, memory: "InteractionMemory") -> None:
        """Copia únicamente el estado resumido específico de SIRAH."""

        self._interaction_memory = memory

    def snapshot(self, session_id: str) -> SystemSnapshot:
        context: PresentContext = self.contexts.get(session_id)
        memory = self._interaction_memory
        return SystemSnapshot(
            session_id=session_id,
            intelligence_provider=self.intelligence_provider,
            components=self.components.all(),
            enabled_capabilities=tuple(
                definition.name for definition in self.catalog.enabled()
            ),
            safety_state=context.safety_state,
            last_capability=context.last_requested_capability,
            last_result=context.last_capability_result,
            recent_message_count=len(context.messages),
            robot_connected=self.robot.is_connected,
            recent_commands=tuple(self._recent_commands),
            recent_events=tuple(self._recent_events),
            safe_errors=tuple(self._safe_errors),
            silent_mode=bool(getattr(memory, "silent_mode", False)),
            autonomy_active=bool(getattr(memory, "autonomy_active", True)),
            tts_active=bool(getattr(memory, "tts_active", False)),
            last_initiative_reason=getattr(memory, "last_reason", None),
        )
