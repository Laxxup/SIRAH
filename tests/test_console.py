"""Test LaboratoryConsole dispatch (no UI)."""

from __future__ import annotations

import asyncio
import pytest

from sirah.console import LaboratoryConsole
from sirah.factory import SystemProfile


@pytest.mark.asyncio
async def test_console_create_and_stop() -> None:
    console = LaboratoryConsole(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="fake",
    )
    console._system = None
    console._running = True
    await asyncio.sleep(0)
    assert console._intelligence_type == "fake"


@pytest.mark.asyncio
async def test_console_command_help() -> None:
    console = LaboratoryConsole(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="fake",
    )
    sys = __import__("sirah.factory", fromlist=["build_system"]).build_system(
        profile=SystemProfile.DEV_LAPTOP, intelligence_type="fake"
    )
    console._system = sys
    await sys.orchestrator.start()

    await console._handle_command("help")
    await console._handle_command("status")
    await console._handle_command("history")
    await console._handle_command("silent")
    await console._handle_command("loud")

    await sys.orchestrator.stop()


@pytest.mark.asyncio
async def test_console_unknown_command() -> None:
    console = LaboratoryConsole(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="fake",
    )
    sys = __import__("sirah.factory", fromlist=["build_system"]).build_system(
        profile=SystemProfile.DEV_LAPTOP, intelligence_type="fake"
    )
    console._system = sys
    await sys.orchestrator.start()

    await console._handle_command("unknown_cmd")

    await sys.orchestrator.stop()


@pytest.mark.asyncio
async def test_console_dispatch_text() -> None:
    from sirah.factory import build_system, SystemProfile

    console = LaboratoryConsole(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="fake",
    )
    sys = build_system(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="fake",
    )
    console._system = sys
    await sys.orchestrator.start()

    await console._dispatch("hola")

    ctx = sys.orchestrator.context
    assert len(ctx.messages) == 2

    await sys.orchestrator.stop()
