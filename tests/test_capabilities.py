"""Pruebas del catálogo y la autoridad local de capacidades."""

import pytest

from sirah.capabilities import (
    CapabilityCatalog,
    CapabilityDefinition,
    CapabilityPolicy,
    CapabilityRequest,
    ParameterDefinition,
)
from sirah.errors import CapabilityRejectedError


def definition(
    name: str = "robot.home",
    *,
    enabled: bool = True,
    parameters: dict[str, ParameterDefinition] | None = None,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=name,
        description="Capacidad de prueba.",
        parameters=parameters or {},
        enabled=enabled,
        translator=lambda request: request,
    )


def test_catalog_rejects_duplicates() -> None:
    catalog = CapabilityCatalog()
    catalog.register(definition())
    with pytest.raises(ValueError, match="duplicada"):
        catalog.register(definition())


def test_catalog_exposes_only_enabled_capabilities() -> None:
    catalog = CapabilityCatalog()
    catalog.register(definition())
    catalog.register(definition("robot.disabled", enabled=False))
    assert [item.name for item in catalog.enabled()] == ["robot.home"]
    assert [item["name"] for item in catalog.safe_prompt_view()] == ["robot.home"]


def test_unknown_capability_is_rejected() -> None:
    policy = CapabilityPolicy(CapabilityCatalog())
    with pytest.raises(CapabilityRejectedError, match="desconocida"):
        policy.authorize(CapabilityRequest("r1", "robot.missing"))


def test_disabled_capability_is_rejected() -> None:
    catalog = CapabilityCatalog()
    catalog.register(definition(enabled=False))
    with pytest.raises(CapabilityRejectedError, match="deshabilitada"):
        CapabilityPolicy(catalog).authorize(
            CapabilityRequest("r1", "robot.home")
        )


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"extra": 1}, "adicionales"),
        ({}, "Faltan"),
        ({"count": "2"}, "Tipo inválido"),
        ({"count": 4}, "fuera de límites"),
    ],
)
def test_parameter_contract_is_enforced(
    parameters: dict[str, object], message: str
) -> None:
    catalog = CapabilityCatalog()
    catalog.register(
        definition(
            parameters={
                "count": ParameterDefinition(int, minimum=1, maximum=3)
            }
        )
    )
    with pytest.raises(CapabilityRejectedError, match=message):
        CapabilityPolicy(catalog).authorize(
            CapabilityRequest("r1", "robot.home", parameters)
        )


def test_non_finite_numeric_parameter_is_rejected() -> None:
    catalog = CapabilityCatalog()
    catalog.register(
        definition(parameters={"ratio": ParameterDefinition(float)})
    )
    with pytest.raises(CapabilityRejectedError, match="no finito"):
        CapabilityPolicy(catalog).authorize(
            CapabilityRequest("r1", "robot.home", {"ratio": float("inf")})
        )


@pytest.mark.parametrize(
    "parameters",
    [
        {"gpio": 1},
        {"PWM-channel": 2},
        {"robot_command": "stop"},
        {"_lock": "open"},
    ],
)
def test_internal_or_electrical_names_are_rejected(
    parameters: dict[str, object],
) -> None:
    catalog = CapabilityCatalog()
    catalog.register(
        definition(
            parameters={
                key: ParameterDefinition(type(value))
                for key, value in parameters.items()
            }
        )
    )
    with pytest.raises(CapabilityRejectedError, match="prohibido"):
        CapabilityPolicy(catalog).authorize(
            CapabilityRequest("r1", "robot.home", parameters)
        )
