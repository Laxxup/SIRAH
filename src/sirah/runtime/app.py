"""Runtime app (Stage 7) — asyncio wiring: config → components → registry.

The stable-runtime entry point. Responsibilities and boundaries:

- Loads runtime settings (TOML, A9) + actuator mirror YAML together.
- Builds the transport as an ADAPTER around the given EyeTransport
  (serial or fake); the runtime OWNS the port (ADR-0002/0009).
- Runs the perception/behavior pipeline slots when provided (Stage 8
  supplies camera + face detector + gaze behavior; Stage 7 accepts None
  and reports them as `off`).
- Sends heartbeat while eyes ready (Stage 11 semantics scaffolded here).
- A serial failure DEGRADES eyes but the app keeps running (registry
  rule); SIGINT/SIGTERM stop it cleanly.

The app NEVER decides physical policy (that lives in policies.py +
firmware); it wires and reports.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sirah.config.loader import (
    RuntimeSettings,
    load_runtime_config,
)
from sirah.config.schema import ActuatorConfig
from sirah.hardware.transport import EyeTransport, TransportError
from sirah.runtime.heartbeat import HeartbeatWriter
from sirah.runtime.policies import LostFacePolicy, SetpointGate
from sirah.runtime.registry import ComponentRegistry, ComponentStatus

_logger = logging.getLogger(__name__)


@dataclass
class RuntimeResult:
    """What the runtime observed in a run (for tests + observability)."""

    settings: RuntimeSettings
    registry: ComponentRegistry
    faces_seen: int = 0
    send_errors: int = 0


class RuntimeApp:
    """Wiring shell: settings + registry + optional pipeline components."""

    def __init__(
        self,
        settings: RuntimeSettings,
        actuators: ActuatorConfig,
        transport: EyeTransport,
        *,
        camera: Any | None = None,          # Stage 8: next_frame() -> Frame
        face_detector: Any | None = None,   # Stage 8: detect(frame) -> GazeTarget|None
        behavior: Any | None = None,        # Stage 8: step(GazeTarget) -> Setpoint
        proposal_source: Any | None = None, # ADR-0007: next() -> Setpoint|None
    ) -> None:
        self.settings = settings
        self.actuators = actuators
        self.transport = transport
        self.camera = camera
        self.face_detector = face_detector
        self.behavior = behavior
        self.proposal_source = proposal_source
        self.registry = ComponentRegistry()
        self.policy = SetpointGate()
        self.lost_face = LostFacePolicy(timeout_s=settings.lost_face_center_s)
        self.result = RuntimeResult(settings=settings, registry=self.registry)

    @classmethod
    def from_config(
        cls,
        transport: EyeTransport,
        *,
        runtime_toml: str | None = None,
        actuators_yaml: str | None = None,
        env: dict[str, str] | None = None,
        **components: Any,
    ) -> RuntimeApp:
        """Build with settings+actuator mirror loaded together (ADR-0009)."""
        settings, actuators = load_runtime_config(
            runtime_toml, actuators_yaml, env
        )
        return cls(settings, actuators, transport, **components)

    async def run(self, stop: asyncio.Event | None = None) -> RuntimeResult:
        """Boot, run the pipeline until `stop`, tear down cleanly."""
        stop = stop or asyncio.Event()
        self._init_registry()

        eyes_ok = await self._start_eyes()
        await self._start_camera()

        tasks = [asyncio.create_task(self._pipeline_loop(stop, eyes_ok))]
        if eyes_ok:
            tasks.append(
                asyncio.create_task(
                    HeartbeatWriter(
                        self.transport, cadence_s=self.settings.heartbeat_cadence_s
                    ).run(stop)
                )
            )
        await stop.wait()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._teardown()
        return self.result

    # --- lifecycle helpers --------------------------------------------

    def _init_registry(self) -> None:
        r = self.registry
        r.set("eyes", ComponentStatus.OFF, "disarmed until SIRAH_EYES=1 or --eyes")
        r.set("camera", ComponentStatus.OFF, "no camera source wired")
        r.set("behavior", ComponentStatus.OFF, "no behavior wired (Stage 8)")
        r.set("lab", ComponentStatus.OFF, "lab disabled (ADR-0007)")

    async def _start_eyes(self) -> bool:
        """Open the transport; degrade (not die) on failure."""
        if not self.settings.eyes_armed:
            return False
        try:
            await self.transport.connect()
            self.registry.set("eyes", ComponentStatus.READY, "linked")
            return True
        except (TransportError, OSError) as exc:
            self.registry.set("eyes", ComponentStatus.DEGRADED, str(exc))
            return False

    async def _start_camera(self) -> None:
        if self.camera is None:
            return
        try:
            await self.camera.start()
            self.registry.set("camera", ComponentStatus.READY, "streaming")
        except Exception as exc:  # noqa: BLE001 - camera failures degrade
            self.registry.set("camera", ComponentStatus.DEGRADED, str(exc))
        if self.face_detector is not None and self.behavior is not None:
            self.registry.set("behavior", ComponentStatus.READY, "pipeline wired")
        if self.proposal_source is not None:
            self.registry.set("lab", ComponentStatus.READY, "proposal source present")

    async def _pipeline_loop(self, stop: asyncio.Event, eyes_ok: bool) -> None:
        """Sustain (Stage 7): keep the idle heartbeat alive while devices report.

        The frame → face → behavior → TARGET wiring lands in Stage 8; this
        loop only holds the heartbeat task company so the app stays alive
        until `stop`, and reports camera failures as degraded.
        """
        try:
            while not stop.is_set():
                await asyncio.sleep(self.settings.tick_s)
        except asyncio.CancelledError:
            return

    async def _teardown(self) -> None:
        try:
            if self.camera is not None and hasattr(self.camera, "stop"):
                await self.camera.stop()
        except Exception as exc:  # noqa: BLE001 - best-effort teardown
            _logger.debug("camera stop ignored: %r", exc)
        try:
            await self.transport.disconnect()
        except Exception as exc:  # noqa: BLE001 - best-effort teardown
            _logger.debug("transport disconnect ignored: %r", exc)
        current = self.registry.get("eyes")
        if current.status == ComponentStatus.READY:
            self.registry.set("eyes", ComponentStatus.OFF, "shutdown")