"""Catálogo y política de capacidades de alto nivel de SIRAH."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from .errors import CapabilityRejectedError

ParameterValue = str | int | float | bool
CapabilityTranslator = Callable[["CapabilityRequest"], object]

_FORBIDDEN_FRAGMENTS = frozenset(
    {
        "__",
        "angle_deg",
        "channel",
        "gpio",
        "lock",
        "pca9685",
        "pulse",
        "pwm",
        "robotcommand",
        "robot_command",
        "robotport",
        "robot_port",
        "servo",
        "transport",
    }
)


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    """Solicitud de una capacidad nominal, nunca de un comando eléctrico."""

    request_id: str
    capability: str
    parameters: Mapping[str, ParameterValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise CapabilityRejectedError("request_id debe ser una cadena no vacía.")
        if not isinstance(self.capability, str) or not self.capability.strip():
            raise CapabilityRejectedError("capability debe ser una cadena no vacía.")
        if not isinstance(self.parameters, Mapping):
            raise CapabilityRejectedError("parameters debe ser un objeto.")
        object.__setattr__(
            self, "parameters", MappingProxyType(dict(self.parameters))
        )


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    """Contrato local de un parámetro seguro de alto nivel."""

    value_type: type[str] | type[int] | type[float] | type[bool]
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """Definición registrada y su traductor determinista hacia Cortex."""

    name: str
    description: str
    parameters: Mapping[str, ParameterDefinition]
    enabled: bool
    translator: CapabilityTranslator

    def __post_init__(self) -> None:
        if not self.name.strip() or self.name.startswith("_"):
            raise ValueError("El nombre de capacidad debe ser público y no vacío.")
        if not self.description.strip():
            raise ValueError("La descripción de capacidad no puede estar vacía.")
        object.__setattr__(
            self, "parameters", MappingProxyType(dict(self.parameters))
        )


class CapabilityCatalog:
    """Registro explícito de capacidades implementadas."""

    def __init__(self) -> None:
        self._definitions: dict[str, CapabilityDefinition] = {}

    def register(self, definition: CapabilityDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Capacidad duplicada: {definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> CapabilityDefinition | None:
        return self._definitions.get(name)

    def enabled(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(
            definition
            for definition in self._definitions.values()
            if definition.enabled
        )

    def safe_prompt_view(self) -> tuple[dict[str, object], ...]:
        """Expone solo nombres y parámetros de alto nivel habilitados."""

        return tuple(
            {
                "name": definition.name,
                "description": definition.description,
                "parameters": {
                    name: {
                        "type": spec.value_type.__name__,
                        "required": spec.required,
                        "minimum": spec.minimum,
                        "maximum": spec.maximum,
                        "description": spec.description,
                    }
                    for name, spec in definition.parameters.items()
                },
            }
            for definition in self.enabled()
        )


class CapabilityPolicy:
    """Autoridad local que valida antes de traducir o ejecutar."""

    def __init__(self, catalog: CapabilityCatalog) -> None:
        self._catalog = catalog

    def authorize(self, request: CapabilityRequest) -> CapabilityDefinition:
        self._reject_internal_names(request)
        definition = self._catalog.get(request.capability)
        if definition is None:
            raise CapabilityRejectedError(
                f"Capacidad desconocida: {request.capability}"
            )
        if not definition.enabled:
            raise CapabilityRejectedError(
                f"Capacidad deshabilitada: {request.capability}"
            )
        self._validate_parameters(request.parameters, definition.parameters)
        return definition

    @staticmethod
    def _reject_internal_names(request: CapabilityRequest) -> None:
        candidates = [request.capability, *request.parameters]
        for candidate in candidates:
            normalized = candidate.lower().replace("-", "_")
            if any(fragment in normalized for fragment in _FORBIDDEN_FRAGMENTS):
                raise CapabilityRejectedError(
                    "La solicitud contiene un nombre interno o mecánico prohibido."
                )

    @staticmethod
    def _validate_parameters(
        supplied: Mapping[str, ParameterValue],
        expected: Mapping[str, ParameterDefinition],
    ) -> None:
        extra = set(supplied) - set(expected)
        if extra:
            raise CapabilityRejectedError(
                f"Parámetros adicionales no permitidos: {sorted(extra)}"
            )
        missing = {
            name
            for name, spec in expected.items()
            if spec.required and name not in supplied
        }
        if missing:
            raise CapabilityRejectedError(
                f"Faltan parámetros requeridos: {sorted(missing)}"
            )
        for name, value in supplied.items():
            spec = expected[name]
            if spec.value_type in {int, float} and isinstance(value, bool):
                raise CapabilityRejectedError(f"Tipo inválido para {name}.")
            if not isinstance(value, spec.value_type):
                raise CapabilityRejectedError(f"Tipo inválido para {name}.")
            if isinstance(value, (int, float)):
                numeric = float(value)
                if not isfinite(numeric):
                    raise CapabilityRejectedError(
                        f"Valor no finito para {name}."
                    )
                if spec.minimum is not None and numeric < spec.minimum:
                    raise CapabilityRejectedError(
                        f"Valor fuera de límites para {name}."
                    )
                if spec.maximum is not None and numeric > spec.maximum:
                    raise CapabilityRejectedError(
                        f"Valor fuera de límites para {name}."
                    )
