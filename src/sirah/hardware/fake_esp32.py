"""FakeESP32 — pure-Python emulation of the ESP32 eyes firmware (Stage 6).

Test double + laboratory device (ADR-0007 mode B, ADR-0010): behaviorally
mirrors the firmware wire contract WITHOUT hardware, and is initialized
from the SAME actuator config YAML the runtime mirror uses (ADR-0009), so
tests and lab mode exercise the real physical limits, not invented ones.

Mirror map (firmware files tell the truth; this module is the mirror):

- grammar acceptance  -> `sirah.protocol.parse_line` (corpus-gated;
  identical verdicts by construction)
- degree mapping      -> `core/mapping.h` (piecewise corners + hard clamp)
- easing              -> `core/easing.cpp` (per-axis k, snap eps, ADR-0005;
  Y damped more than X)
- blink FSM           -> `core/blink_fsm.cpp` (Idle/Closing/Closed/Opening,
  trigger only in Idle, auto cadence drawn with jitter, seeded RNG)
- replies             -> `core/protocol.cpp` (`READY 1`, `OK`, `ERR n`,
  `STATE %.3f %.3f %d` with the -0.000 clamp)
- watchdog            -> Stage 11 semantics (countdown from last
  HEARTBEAT; on timeout target eases back to CENTER; blink continues)

Evidence classes: mapping/easing/FSM/reply formatting VERIFIED against
the C++ host tests (same numbers); tick period 20 ms INFERRED from the
firmware task loop; watchdog timing per the Stage 11 plan (proposed
1 s cadence / 3 s timeout). Drift between fake and firmware is caught by
the golden corpus (parser) + Stage 10/14 HIL gates (behavior).

Parity notes (documented differences):
- The fake runs on the test machine's clock; it does not drive real PWM
  or real I2C, so actuator wiring (channels) is config data, not behavior.
- Cadence jitter uses a seeded RNG for determinism; the firmware uses
  esp_random (non-deterministic by design — cadence is observed, not
  asserted, on hardware, Stage 10).
- No serial framing is simulated: the fake receives and replies whole
  lines, like the adapter boundary does (framing is tested in Stage 5).
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from sirah.config.schema import ActuatorConfig, load_actuator_config
from sirah.hardware.transport import (
    EyeTransport,
    ReadTimeout,
    TransportState,
    TransportStatus,
)
from sirah.protocol.parse_line import parse_line

# Per-axis easing constants (ADR-0005: Y damped more than X).
# VERIFIED against firmware host tests (core_tests.cpp uses these).
EASE_KX = 0.25
EASE_KY = 0.12
SNAP_EPS = 0.001

MIN_COORD = -1.0
MAX_COORD = 1.0

DEFAULT_TICK_MS = 20  # INFERRED from the firmware task loop
DEFAULT_READ_TIMEOUT_S = 1.0
DEFAULT_WATCHDOG_TIMEOUT_MS = 3000  # Stage 11 plan: proposed 3 s timeout

_Clock = Callable[[], float]


def _monotonic_ms() -> float:
    return time.monotonic() * 1000.0


def map_piecewise(
    n: float,
    n0: float,
    d0: float,
    n1: float,
    d1: float,
    n2: float,
    d2: float,
) -> float:
    """Mirror of core/mapping.cpp piecewise_map: clamp input to [n0,n2],
    interpolate through (n1,d1), clamp output to the degree span (hard
    clamp, ADR-0004)."""
    n = max(min(n, n2), n0)
    deg = d0 + (n - n0) * (d1 - d0) / (n1 - n0) if n <= n1 else d1 + (n - n1) * (d2 - d1) / (n2 - n1)
    lo, hi = min(d0, d2), max(d0, d2)
    return max(min(deg, hi), lo)


def clamp_deg(deg: float, lo_deg: float, hi_deg: float) -> float:
    """Degree-range hard clamp (mirror of clamp_deg_x/y, mapping.h)."""
    return max(min(deg, hi_deg), lo_deg)


def eyelid_position(open_deg: float, closed_deg: float, t: float) -> float:
    """Eyelid linear interpolation, t in [0,1]: 0 open -> 1 closed."""
    t = max(min(t, 1.0), 0.0)
    return open_deg + (closed_deg - open_deg) * t


class BlinkState:
    IDLE = "idle"
    CLOSING = "closing"
    CLOSED = "closed"
    OPENING = "opening"


@dataclass
class BlinkConfig:
    closing_ms: int = 150
    closed_ms: int = 300  # physical evidence: ~300 ms travel before reopen
    opening_ms: int = 180
    cadence_ms: int = 6000  # natural cadence 6 s ± jitter (A10)
    jitter_ms: int = 2000
    min_cycle_gap_ms: int = 1000


class GazeEaser:
    """Mirror of core/easing.cpp (snap eps, no overshoot by construction)."""

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0

    def tick(self, target_x: float, target_y: float, kx: float, ky: float) -> bool:
        self.x += (target_x - self.x) * kx
        self.y += (target_y - self.y) * ky
        settled = True
        if abs(target_x - self.x) < SNAP_EPS:
            self.x = target_x
        else:
            settled = False
        if abs(target_y - self.y) < SNAP_EPS:
            self.y = target_y
        else:
            settled = False
        return settled


class BlinkFSM:
    """Mirror of core/blink_fsm.cpp (deterministic with a seeded RNG)."""

    def __init__(self, config: BlinkConfig | None = None, seed: int | None = None) -> None:
        self.config = config or BlinkConfig()
        self._rng = random.Random(seed)
        self._state = BlinkState.IDLE
        self._entered_ms = 0.0
        self._last_cycle_end_ms = 0.0
        self._armed = False

    @property
    def state(self) -> str:
        return self._state

    def trigger(self, now_ms: float) -> None:
        """Best-effort: one blink if Idle, discarded otherwise (A4/A10)."""
        if self._state == BlinkState.IDLE:
            self._enter(BlinkState.CLOSING, now_ms)

    def reset(self) -> None:
        self._state = BlinkState.IDLE
        self._entered_ms = 0.0
        self._last_cycle_end_ms = 0.0
        self._armed = False

    def tick(self, now_ms: float, auto_interval_ms: int) -> None:
        """One loop tick; auto_interval_ms is the drawn cadence (jitter)."""
        cfg = self.config
        if self._state == BlinkState.IDLE:
            if not self._armed:
                self._armed = True
                self._last_cycle_end_ms = now_ms
                return
            if now_ms - self._last_cycle_end_ms < cfg.min_cycle_gap_ms:
                return
            if now_ms - self._last_cycle_end_ms >= auto_interval_ms:
                self._enter(BlinkState.CLOSING, now_ms)
        elif self._state == BlinkState.CLOSING:
            if now_ms - self._entered_ms >= cfg.closing_ms:
                self._enter(BlinkState.CLOSED, now_ms)
        elif self._state == BlinkState.CLOSED:
            if now_ms - self._entered_ms >= cfg.closed_ms:
                self._enter(BlinkState.OPENING, now_ms)
        elif self._state == BlinkState.OPENING:
            if now_ms - self._entered_ms >= cfg.opening_ms:
                self._state = BlinkState.IDLE
                self._last_cycle_end_ms = now_ms

    def progress(self, now_ms: float) -> float:
        """Eyelid progress 0 (open) ... 1 (closed sustained) ... 0 (open)."""
        elapsed = now_ms - self._entered_ms
        cfg = self.config
        if self._state == BlinkState.CLOSING:
            d = cfg.closing_ms
            return 1.0 if elapsed >= d else elapsed / d
        if self._state == BlinkState.CLOSED:
            return 1.0
        if self._state == BlinkState.OPENING:
            d = cfg.opening_ms
            t = 1.0 if elapsed >= d else elapsed / d
            return 1.0 - t
        return 0.0

    def draw_interval_ms(self) -> int:
        """Current drawn auto cadence (seeded for determinism)."""
        cfg = self.config
        lo = cfg.cadence_ms - cfg.jitter_ms
        hi = cfg.cadence_ms + cfg.jitter_ms
        return self._rng.randint(lo, hi)

    def _enter(self, state: str, now_ms: float) -> None:
        self._state = state
        self._entered_ms = now_ms


class FakeESP32(EyeTransport):
    """In-memory firmware double: EyeTransport port (Stage 5 shape).

    Constructor takes the SAME ActuatorConfig the runtime uses (ADR-0009).
    Time advances on a virtual clock; tests may inject a manual clock to
    step deterministically (ADR-0010), while the default tracks wall time.
    """

    def __init__(
        self,
        config: ActuatorConfig | None = None,
        *,
        tick_ms: int = DEFAULT_TICK_MS,
        blink_config: BlinkConfig | None = None,
        seed: int | None = None,
        watchdog_timeout_ms: int = DEFAULT_WATCHDOG_TIMEOUT_MS,
        read_timeout_s: float = DEFAULT_READ_TIMEOUT_S,
        clock: _Clock | None = None,
    ) -> None:
        self.config: ActuatorConfig = config or load_actuator_config()
        self.tick_ms = tick_ms
        self.watchdog_timeout_ms = watchdog_timeout_ms
        self._blink = BlinkFSM(blink_config, seed)
        self._read_timeout_s = read_timeout_s
        self._clock: _Clock = clock or _monotonic_ms
        self._easer = GazeEaser()
        self._pending: deque[bytes] = deque()
        self._status = TransportStatus(TransportState.DISCONNECTED)
        self._target_x = 0.0
        self._target_y = 0.0
        self._last_heartbeat_ms: float | None = None
        self._sim_ms = 0.0  # virtual simulation clock
        self._last_sync_ms: float | None = None

    @classmethod
    def from_actuators_yaml(
        cls, path: str | None = None, **kwargs: object
    ) -> FakeESP32:
        """Build from the shared actuator YAML (ADR-0009 baseline)."""
        return cls(load_actuator_config(path), **kwargs)  # type: ignore[arg-type]

    # --- EyeTransport lifecycle ---------------------------------------

    async def connect(self) -> None:
        if self._status.state is TransportState.CONNECTED:
            return
        self._status = TransportStatus(TransportState.CONNECTED)
        self._last_sync_ms = self._clock()
        self._enqueue(b"READY 1")

    async def disconnect(self) -> None:
        self._pending.clear()
        self._status = TransportStatus(TransportState.DISCONNECTED)

    async def send(self, payload: bytes) -> None:
        self._sync()
        result = parse_line(payload)
        if result.kind == "err":
            self._enqueue(f"ERR {result.code}".encode())
            return
        if result.kind != "cmd":
            # Responses/ignored arriving at the firmware produce no reply.
            return
        assert result.name is not None
        if result.name == "TARGET":
            x, y = float(result.args[0]), float(result.args[1])
            if not (MIN_COORD <= x <= MAX_COORD and MIN_COORD <= y <= MAX_COORD):
                self._enqueue(b"ERR 3")  # parser already guards; belt & suspenders
                return
            self._target_x, self._target_y = x, y
            self._enqueue(b"OK")
        elif result.name == "CENTER":
            self._target_x = self._target_y = 0.0
            self._enqueue(b"OK")
        elif result.name == "BLINK":
            self._blink.trigger(self._sim_ms)
            self._enqueue(b"OK")
        elif result.name == "HEARTBEAT":
            self._last_heartbeat_ms = self._sim_ms  # silent by spec 6.2
        elif result.name == "STATUS":
            self._enqueue(self._format_state())
        else:  # pragma: no cover - parse_line only yields the verbs above
            raise AssertionError(f"unreachable command: {result.name}")

    async def read(self, timeout: float | None = None) -> bytes | None:
        self._sync()
        seconds = self._read_timeout_s if timeout is None else timeout
        if self._pending:
            return self._pending.popleft()
        try:
            await asyncio.wait_for(self._await_reply(), timeout=seconds)
        except TimeoutError:
            raise ReadTimeout(f"fake esp32: no reply within {seconds}s") from None
        return self._pending.popleft()

    def status(self) -> TransportStatus:
        self._sync()
        return self._status

    # --- virtual time / simulation ------------------------------------

    def advance(self, ms: float) -> None:
        """Step the virtual simulation clock by ms (deterministic tests).

        With an injected manual clock (ADR-0010) the test controls time
        exactly; with the default wall clock, advance() jumps the sim ahead
        by ms. Always connected: advances run the easing/blink/watchdog.
        """
        self._advance(ms)

    async def peek(self) -> bytes | None:
        """Next pending reply without consuming (test helper)."""
        self._sync()
        return self._pending[0] if self._pending else None

    # --- internals -----------------------------------------------------

    def _advance(self, ms: float) -> None:
        steps = int(ms // self.tick_ms)
        for _ in range(steps):
            self._sim_ms += self.tick_ms
            self._step(self._sim_ms)
        self._sim_ms += ms - steps * self.tick_ms

    def _enqueue(self, reply: bytes) -> None:
        self._pending.append(reply)

    def _sync(self) -> None:
        """Run simulation steps until caught up with the wall clock."""
        now = self._clock()
        if self._last_sync_ms is None:
            self._last_sync_ms = now
            return
        delta = now - self._last_sync_ms
        if delta <= 0:
            return
        self._advance(delta)
        self._last_sync_ms = now

    def _step(self, now_ms: float) -> None:
        # Watchdog (Stage 11): countdown from last HEARTBEAT; on timeout the
        # target eases back to CENTER. Blink continues (firmware-owned).
        if (
            self._last_heartbeat_ms is not None
            and now_ms - self._last_heartbeat_ms >= self.watchdog_timeout_ms
        ):
            self._target_x = 0.0
            self._target_y = 0.0
        self._easer.tick(self._target_x, self._target_y, EASE_KX, EASE_KY)
        interval = self._blink.draw_interval_ms()
        self._blink.tick(now_ms, interval)

    def _format_state(self) -> bytes:
        x, y = self._easer.x, self._easer.y
        if -0.0005 < x < 0.0:
            x = 0.0
        if -0.0005 < y < 0.0:
            y = 0.0
        blink = 1 if self._blink.progress(self._sim_ms) > 0 else 0
        return f"STATE {x:.3f} {y:.3f} {blink}".encode()

    async def _await_reply(self) -> None:
        while not self._pending:
            await asyncio.sleep(0.01)