"""Test capability catalog and policy."""

from __future__ import annotations

import pytest

from sirah.action.capabilities import CapabilityCatalog, CapabilityPolicy
from sirah.types import CapabilityDefinition, CapabilityRequest
from sirah.errors import CapabilityNotFoundError, CapabilityRejectedError


def test_catalog_defaults() -> None:
    catalog = CapabilityCatalog()
    assert len(catalog.list()) >= 3
    assert "robot.greet" in catalog.list()
    assert "robot.stop" in catalog.list()
    assert "robot.home" in catalog.list()


def test_catalog_get_existing() -> None:
    catalog = CapabilityCatalog()
    d = catalog.get("robot.greet")
    assert d.name == "robot.greet"
    assert d.category == "social"


def test_catalog_get_not_found() -> None:
    catalog = CapabilityCatalog()
    with pytest.raises(CapabilityNotFoundError):
        catalog.get("nonexistent")


def test_catalog_register_custom() -> None:
    catalog = CapabilityCatalog()
    d = CapabilityDefinition(
        name="custom.action",
        description="custom",
        category="custom",
    )
    catalog.register(d)
    assert "custom.action" in catalog.list()
    assert catalog.get("custom.action").category == "custom"


def test_policy_authorize_allowed() -> None:
    policy = CapabilityPolicy()
    req = CapabilityRequest(name="robot.greet")
    assert policy.authorize(req) is True


def test_policy_authorize_forbidden() -> None:
    policy = CapabilityPolicy(forbidden=frozenset({"robot.stop"}))
    req = CapabilityRequest(name="robot.stop")
    with pytest.raises(CapabilityRejectedError):
        policy.authorize(req)


def test_policy_forbid_and_allow() -> None:
    policy = CapabilityPolicy()
    policy.forbid("robot.greet")
    with pytest.raises(CapabilityRejectedError):
        policy.authorize(CapabilityRequest(name="robot.greet"))
    policy.allow("robot.greet")
    assert policy.authorize(CapabilityRequest(name="robot.greet")) is True
