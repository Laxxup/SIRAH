"""Perception contracts (Stage 8): nominal types between runtime layers.

Perception DESCRIBES the world; behavior DECIDES; firmware does the
physical (ADR-0004). These are the nominal Protocols (typing.Protocol,
runtime-checkable) that the runtime wires — declared HERE, not in
runtime/app.py, so mypy catches contract disagreements at type time and
any camera/detector implementation (fake, replay, OpenCV+Yunet) satisfies
the same shape.

Base install stays zero-dependency: no numpy, no OpenCV — `Frame.payload`
is an opaque slot for whichever source provides images (Stage 8 real
camera fills it; tests/fakes leave it None).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal, Protocol, runtime_checkable

SourceState = Literal["tracking", "lost", "searching"]


@dataclass(frozen=True)
class Frame:
    """One captured frame. `index` is the monotonic sequence number.

    `payload` carries the source-specific image (e.g. a numpy BGR array
    from OpenCV) without importing it here; the detector is the only
    consumer that needs to know the concrete type. `captured_at` is the
    source's monotonic capture timestamp so consumers can measure frame
    age without importing a clock (freshness > processing every frame).
    """

    index: int
    payload: object | None = None
    captured_at: float | None = None

    def __post_init__(self) -> None:
        if self.captured_at is not None and not isfinite(self.captured_at):
            raise ValueError("captured_at must be finite")


@dataclass(frozen=True)
class GazeTarget:
    """What perception measured about the face, in A1 normalized world
    coordinates: x -1 left / 0 center / +1 right; y -1 down / 0 center /
    +1 up. `confidence` in [0, 1] so behavior can weigh weak detections.
    """

    x: float
    y: float
    confidence: float = 1.0


@dataclass(frozen=True)
class PerceptionSnapshot:
    """Derived semantic observation for event and shadow-only behavior layers."""

    observed_at: float
    present: bool
    x: float | None
    y: float | None
    confidence: float | None
    source_state: SourceState

    def __post_init__(self) -> None:
        if not isfinite(self.observed_at):
            raise ValueError("observed_at must be finite")
        values = (self.x, self.y, self.confidence)
        if self.source_state == "tracking":
            if not self.present or any(value is None for value in values):
                raise ValueError("tracking snapshots require present coordinates")
            assert self.x is not None and self.y is not None and self.confidence is not None
            if not -1.0 <= self.x <= 1.0 or not -1.0 <= self.y <= 1.0:
                raise ValueError("tracking coordinates must be normalized")
            if not 0.0 <= self.confidence <= 1.0:
                raise ValueError("tracking confidence must be normalized")
        elif self.source_state in {"lost", "searching"}:
            if self.present or any(value is not None for value in values):
                raise ValueError("lost/searching snapshots require absent coordinates")
        else:  # pragma: no cover - Literal is enforced statically
            raise ValueError("unknown source_state")


def snapshot_from_target(
    target: GazeTarget | None,
    *,
    observed_at: float,
    absent_state: Literal["lost", "searching"] = "searching",
) -> PerceptionSnapshot:
    """Adapt the Stage 8 detector output without exposing frame payloads."""
    if target is None:
        return PerceptionSnapshot(observed_at, False, None, None, None, absent_state)
    return PerceptionSnapshot(
        observed_at, True, target.x, target.y, target.confidence, "tracking"
    )


@runtime_checkable
class CameraSource(Protocol):
    """Frame producer. `next_frame()` returns None when no frame is
    available yet (or the stream ended); the owner decides degradation.
    """

    async def start(self) -> None: ...

    async def next_frame(self) -> Frame | None: ...

    async def stop(self) -> None: ...


@runtime_checkable
class FaceDetector(Protocol):
    """Frame → gaze target. Stateless by design: entry/exit hysteresis
    belongs to the pipeline around it (N frames), not to the detector.
    """

    def detect(self, frame: Frame) -> GazeTarget | None: ...


@runtime_checkable
class MultiFaceDetector(Protocol):
    """Frame → zero or more normalized faces.

    Detection OBSERVES every face; choosing the primary target is a
    separate attention responsibility (attention layer, not the detector).
    Implementations that only satisfy `FaceDetector` remain valid.
    """

    def detect_many(self, frame: Frame) -> Sequence[GazeTarget]: ...
