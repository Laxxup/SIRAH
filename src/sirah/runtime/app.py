"""Runtime app (Stage 8) — asyncio wiring: config → components → registry.

The stable-runtime entry point. Responsibilities and boundaries:

- Loads runtime settings (TOML, A9) + actuator mirror YAML together.
- Builds the transport as an ADAPTER around the given EyeTransport
  (serial or fake); the runtime OWNS the port (ADR-0002/0009).
- Runs the perception/behavior pipeline (Stage 8): camera frame →
  detector → gaze behavior → SetpointGate → TARGET, wired when the
  nominal contracts are provided (src/sirah/perception|behavior). Any
  component failure DEGRADES its registry entry and the app keeps
  running (registry rule).
- Lost-face: when no face arrives for `lost_face_center_s`, the policy
  recenters to CENTER (wired here, Stage 8).
- Sends heartbeat while eyes ready (Stage 11 semantics scaffolded).
- SIGINT/SIGTERM stop it cleanly.

The app NEVER decides physical policy (that lives in policies.py +
firmware); it wires and reports.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sirah.behavior.contracts import Behavior
from sirah.config.loader import (
    RuntimeSettings,
    load_runtime_config,
)
from sirah.config.schema import ActuatorConfig
from sirah.hardware.contract import encode_command
from sirah.hardware.transport import EyeTransport, TransportError
from sirah.perception.contracts import CameraSource, FaceDetector
from sirah.runtime.eye_link_supervisor import EyeLinkSupervisor
from sirah.runtime.policies import LostFacePolicy, SetpointGate
from sirah.runtime.registry import ComponentRegistry, ComponentStatus

_logger = logging.getLogger(__name__)


@dataclass
class RuntimeResult:
    """What the runtime observed in a run (for tests + observability)."""

    settings: RuntimeSettings
    registry: ComponentRegistry
    frames_seen: int = 0  # frames received from the camera source
    faces_seen: int = 0  # frames with a confident detection (wired Stage 8)
    send_errors: int = 0  # outbound eye commands that failed mid-session


class RuntimeApp:
    """Wiring shell: settings + registry + optional pipeline components."""

    def __init__(
        self,
        settings: RuntimeSettings,
        actuators: ActuatorConfig,
        transport: EyeTransport,
        *,
        camera: CameraSource | None = None,
        face_detector: FaceDetector | None = None,
        behavior: Behavior | None = None,
        proposal_source: object | None = None,  # ADR-0007: next() -> Setpoint|None
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
        self._eyes_lost = False
        self._eye_link: EyeLinkSupervisor | None = None
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
            self._eye_link = EyeLinkSupervisor(
                self.transport,
                heartbeat_cadence_s=self.settings.heartbeat_cadence_s,
                read_timeout_s=self.settings.read_timeout_s,
                liveness_timeout_s=self.settings.heartbeat_timeout_s,
                on_link_lost=self._degrade_eyes,
            )
            tasks.append(
                asyncio.create_task(self._eye_link.run(stop))
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
        """Stage 8: frame → detect → behavior → gate → TARGET.

        When the perception/behavior contracts are wired, each tick pulls
        one frame, converts it to a gaze intention and sends the gated
        setpoint. A camera/detector/transport failure DEGRADES its
        component and the loop continues sleeping — the runtime never
        dies from a broken sensor (registry rule); lost-face recenters
        after `lost_face_center_s` (cabled here).
        """
        try:
            while not stop.is_set():
                await self._pipeline_tick()
                await asyncio.sleep(self.settings.tick_s)
        except asyncio.CancelledError:
            return

    async def _pipeline_tick(self) -> None:
        """One pipeline cycle; never raises (transient failures degrade)."""
        if self.camera is None or self.face_detector is None or self.behavior is None:
            return
        try:
            frame = await self.camera.next_frame()
        except Exception as exc:  # noqa: BLE001 - camera failures degrade
            self.registry.set("camera", ComponentStatus.DEGRADED, str(exc))
            self.camera = None
            return
        if frame is None:
            return  # no frame this tick: hold the current gaze
        self.result.frames_seen += 1
        try:
            target = self.face_detector.detect(frame)
        except Exception as exc:  # noqa: BLE001 - detector failures degrade
            self.registry.set("behavior", ComponentStatus.DEGRADED, str(exc))
            self.face_detector = None
            return

        if target is None or target.confidence <= 0.0:
            setpoint = self.lost_face.target()  # CENTER after timeout
        else:
            self.lost_face.on_face()
            self.result.faces_seen += 1
            try:
                setpoint = self.behavior.step(target)
            except Exception as exc:  # noqa: BLE001 - behavior failures degrade
                self.registry.set("behavior", ComponentStatus.DEGRADED, str(exc))
                self.behavior = None
                return
        if setpoint is None:
            return
        gated = self.policy.validate(setpoint.x, setpoint.y)
        if gated is None:
            return  # SetpointGate rejected (out of contract) — nothing sent
        if self._eyes_lost or self._eye_link is None:
            return
        payload = encode_command("TARGET", (gated.x, gated.y))
        await self._eye_link.submit(payload)

    def _degrade_eyes(self, exc: Exception) -> None:
        """Record the first eye-link failure and stop further TARGET sends."""
        if self._eyes_lost:
            return
        self.result.send_errors += 1
        self._eyes_lost = True
        self.registry.set("eyes", ComponentStatus.DEGRADED, str(exc))

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
