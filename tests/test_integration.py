"""Integration test: full pipeline with fake components."""

from __future__ import annotations

import pytest

from sirah.factory import SystemProfile, build_system


@pytest.mark.asyncio
async def test_full_pipeline_conversation() -> None:
    sys = build_system(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="laboratory",
    )
    await sys.orchestrator.start()
    assert sys.orchestrator.is_running

    result = await sys.orchestrator.handle_text("Hola, ¿cómo estás?")
    assert result.message.role == "assistant"
    assert "Hola" in result.message.content or "SIRAH" in result.message.content

    await sys.orchestrator.stop()
    assert not sys.orchestrator.is_running


@pytest.mark.asyncio
async def test_full_pipeline_multi_turn() -> None:
    sys = build_system(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="scripted",
    )
    await sys.orchestrator.start()

    r1 = await sys.orchestrator.handle_text("primero")
    r2 = await sys.orchestrator.handle_text("segundo")
    r3 = await sys.orchestrator.handle_text("tercero")

    assert r1.message.content is not None
    assert r2.message.content is not None
    assert r3.message.content is not None

    ctx = sys.orchestrator.context
    assert len(ctx.messages) == 6

    snap = sys.orchestrator.snapshot
    assert snap.healthy()

    await sys.orchestrator.stop()


@pytest.mark.asyncio
async def test_full_pipeline_stop_command() -> None:
    sys = build_system(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="laboratory",
    )
    await sys.orchestrator.start()

    result = await sys.orchestrator.handle_text("para")
    assert "Deteniéndome" in result.message.content

    await sys.orchestrator.stop()


@pytest.mark.asyncio
async def test_full_pipeline_situational_integration() -> None:
    sys = build_system(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="fake",
    )
    await sys.orchestrator.start()

    assert sys.situational is not None
    await sys.situational.start()
    assert sys.situational.memory.is_empty

    await sys.situational.stop()
    await sys.orchestrator.stop()


@pytest.mark.asyncio
async def test_full_pipeline_tts_integration() -> None:
    sys = build_system(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="fake",
    )
    await sys.orchestrator.start()

    result = await sys.orchestrator.say("hola mundo")
    assert result.success

    await sys.orchestrator.stop()
