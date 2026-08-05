"""Test Groq intelligence parsing and error handling (no network)."""

from __future__ import annotations

import pytest

from sirah.intelligence.groq_adapter import GroqIntelligence
from sirah.errors import (
    IntelligenceUnavailableError,
    IntelligenceTimeoutError,
)


@pytest.mark.asyncio
async def test_groq_health_without_key() -> None:
    intel = GroqIntelligence(api_key=None)
    assert await intel.health() is False


@pytest.mark.asyncio
async def test_groq_health_with_key() -> None:
    intel = GroqIntelligence(api_key="test-key")
    assert await intel.health() is True


@pytest.mark.asyncio
async def test_groq_parse_valid_json() -> None:
    intel = GroqIntelligence(api_key="test-key")
    raw = '{"text_response": "hola", "capability_name": null, "capability_params": {}}'
    decision = intel._parse_decision(raw)
    assert decision.text_response == "hola"
    assert decision.capability_name is None
    assert decision.confidence == 0.95


@pytest.mark.asyncio
async def test_groq_parse_with_capability() -> None:
    intel = GroqIntelligence(api_key="test-key")
    raw = (
        '{"text_response": "saludando", '
        '"capability_name": "robot.greet", '
        '"capability_params": {"style": "wave"}}'
    )
    decision = intel._parse_decision(raw)
    assert decision.text_response == "saludando"
    assert decision.capability_name == "robot.greet"
    assert decision.capability_params == {"style": "wave"}


@pytest.mark.asyncio
async def test_groq_parse_invalid_json_fallback() -> None:
    intel = GroqIntelligence(api_key="test-key")
    raw = "solo texto sin json"
    decision = intel._parse_decision(raw)
    assert decision.text_response == "solo texto sin json"
    assert decision.capability_name is None
    assert decision.confidence == 0.6
