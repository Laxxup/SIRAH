"""Capability catalog and policy — robot capability registry."""

from __future__ import annotations

from sirah.errors import CapabilityNotFoundError, CapabilityRejectedError
from sirah.types import CapabilityDefinition, CapabilityRequest

__all__ = ["CapabilityCatalog", "CapabilityPolicy"]


class CapabilityCatalog:
    def __init__(self) -> None:
        self._definitions: dict[str, CapabilityDefinition] = {}
        self._register_defaults()

    def register(self, definition: CapabilityDefinition) -> None:
        self._definitions[definition.name] = definition

    def get(self, name: str) -> CapabilityDefinition:
        if name not in self._definitions:
            raise CapabilityNotFoundError(f"capability '{name}' not found")
        return self._definitions[name]

    def list(self) -> tuple[str, ...]:
        return tuple(self._definitions.keys())

    def _register_defaults(self) -> None:
        defaults = [
            CapabilityDefinition(
                name="robot.greet",
                description="Greet a person with body gesture",
                category="social",
                requires_safety=False,
                timeout_ms=10_000,
            ),
            CapabilityDefinition(
                name="robot.stop",
                description="Stop all motion immediately",
                category="emergency",
                requires_safety=True,
                timeout_ms=1_000,
            ),
            CapabilityDefinition(
                name="robot.home",
                description="Return to home position",
                category="motion",
                requires_safety=True,
                timeout_ms=30_000,
            ),
            CapabilityDefinition(
                name="robot.look_at",
                description="Turn head toward a person",
                category="social",
                parameters=({"name": "target_x", "type": "float"}, {"name": "target_y", "type": "float"}),
                requires_safety=True,
                timeout_ms=5_000,
            ),
        ]
        for d in defaults:
            self.register(d)


class CapabilityPolicy:
    def __init__(self, forbidden: frozenset[str] | None = None) -> None:
        self._forbidden = forbidden or frozenset()

    def authorize(self, request: CapabilityRequest) -> bool:
        if request.name in self._forbidden:
            raise CapabilityRejectedError(f"capability '{request.name}' forbidden")
        return True

    def forbid(self, name: str) -> None:
        self._forbidden = self._forbidden | {name}

    def allow(self, name: str) -> None:
        self._forbidden = self._forbidden - {name}
