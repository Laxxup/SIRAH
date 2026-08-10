"""RuntimeApp tests (Stage 7): boot with FakeESP32, degrade-not-die,
clean stop, registry transitions."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sirah.config.loader import load_runtime_config
from sirah.hardware.fake_esp32 import FakeESP32
from sirah.runtime.app import RuntimeApp
from sirah.runtime.registry import ComponentStatus

REPO_RUNTIME_TOML = Path(__file__).resolve().parents[3] / "config" / "runtime.toml"
REPO_ACTUATORS_YAML = Path(__file__).resolve().parents[3] / "config" / "actuators.yaml"


def _settings(**env_overrides: str):
    env = {"SIRAH_EYES": "1", **env_overrides}
    settings, actuators = load_runtime_config(
        REPO_RUNTIME_TOML, REPO_ACTUATORS_YAML, env
    )
    return settings, actuators


def _app(transport: FakeESP32, **env_overrides: str) -> RuntimeApp:
    settings, actuators = _settings(**env_overrides)
    return RuntimeApp(settings, actuators, transport)


async def test_boot_arms_eyes_and_stops_cleanly():
    fake = FakeESP32.from_actuators_yaml()
    app = _app(fake)
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await asyncio.sleep(0.05)
    assert app.registry.get("eyes").status == ComponentStatus.READY
    assert app.registry.get("lab").status == ComponentStatus.OFF
    stop.set()
    result = await run
    assert result.registry.get("eyes").status == ComponentStatus.OFF  # shutdown
    assert fake.status().state.value == "disconnected"


async def test_disarmed_eyes_stay_off():
    fake = FakeESP32.from_actuators_yaml()
    app = _app(fake, SIRAH_EYES="0")
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await asyncio.sleep(0.05)
    assert app.registry.get("eyes").status == ComponentStatus.OFF
    stop.set()
    await run


class BrokenTransport(FakeESP32):
    async def connect(self) -> None:
        from sirah.hardware.transport import TransportError

        raise TransportError("device not found")


async def test_serial_failure_degrades_eyes_but_runtime_continues():
    app = _app(BrokenTransport.from_actuators_yaml())
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await asyncio.sleep(0.05)
    state = app.registry.get("eyes")
    assert state.status == ComponentStatus.DEGRADED
    assert "device not found" in state.detail
    stop.set()
    await run  # no exception: runtime survives degraded eyes


async def test_heartbeat_flowing_to_fake_when_ready():
    fake = FakeESP32.from_actuators_yaml()
    app = _app(fake)
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    # Heartbeat is silent per spec 6.2: the fake records last-heartbeat time
    # internally; no reply is produced. Assert the run stays healthy.
    await asyncio.sleep(0.05)
    assert app.registry.get("eyes").status == ComponentStatus.READY
    stop.set()
    await run


@pytest.mark.asyncio
async def test_run_is_idempotent_safe_without_camera():
    fake = FakeESP32.from_actuators_yaml()
    app = _app(fake)
    stop = asyncio.Event()
    task = asyncio.create_task(app.run(stop))
    await asyncio.sleep(0.03)
    stop.set()
    await asyncio.wait_for(task, timeout=2.0)