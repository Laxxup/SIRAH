"""Test intelligence port and adapters."""

from __future__ import annotations

import pytest

from sirah.intelligence.demo_adapter import LaboratoryIntelligence
from sirah.intelligence.fake_adapter import FakeIntelligence
from sirah.types import (
    ConversationMessage,
    IntelligenceRequest,
)


@pytest.mark.asyncio
async def test_fake_intelligence_returns_scripted() -> None:
    intel = FakeIntelligence(scripted=["respuesta 1", "respuesta 2"])
    req = IntelligenceRequest(messages=())
    r1 = await intel.decide(req)
    r2 = await intel.decide(req)
    assert r1.decision is not None
    assert r1.decision.text_response == "respuesta 1"
    assert r2.decision is not None
    assert r2.decision.text_response == "respuesta 2"


@pytest.mark.asyncio
async def test_fake_intelligence_repeats_last() -> None:
    intel = FakeIntelligence(scripted=["única"])
    req = IntelligenceRequest(messages=())
    await intel.decide(req)
    r2 = await intel.decide(req)
    assert r2.decision is not None
    assert r2.decision.text_response == "única"


@pytest.mark.asyncio
async def test_fake_intelligence_health() -> None:
    intel = FakeIntelligence()
    assert await intel.health() is True


@pytest.mark.asyncio
async def test_fake_intelligence_reset() -> None:
    intel = FakeIntelligence(scripted=["a", "b"])
    req = IntelligenceRequest(messages=())
    await intel.decide(req)
    assert intel._index == 1
    intel.reset()
    assert intel._index == 0


@pytest.mark.asyncio
async def test_laboratory_greeting() -> None:
    intel = LaboratoryIntelligence()
    msgs = (ConversationMessage(role="user", content="Hola"),)
    req = IntelligenceRequest(messages=msgs)
    r = await intel.decide(req)
    assert r.decision is not None
    assert "Hola" in r.decision.text_response


@pytest.mark.asyncio
async def test_laboratory_farewell() -> None:
    intel = LaboratoryIntelligence()
    msgs = (ConversationMessage(role="user", content="Adiós"),)
    req = IntelligenceRequest(messages=msgs)
    r = await intel.decide(req)
    assert r.decision is not None
    assert "luego" in r.decision.text_response.lower()


@pytest.mark.asyncio
async def test_laboratory_stop() -> None:
    intel = LaboratoryIntelligence()
    msgs = (ConversationMessage(role="user", content="para"),)
    req = IntelligenceRequest(messages=msgs)
    r = await intel.decide(req)
    assert r.decision is not None
    assert "Deteniéndome" in r.decision.text_response


@pytest.mark.asyncio
async def test_laboratory_default() -> None:
    intel = LaboratoryIntelligence()
    msgs = (ConversationMessage(role="user", content="xyz123"),)
    req = IntelligenceRequest(messages=msgs)
    r = await intel.decide(req)
    assert r.decision is not None
    assert len(r.decision.text_response) > 0
