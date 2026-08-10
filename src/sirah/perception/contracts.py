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

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Frame:
    """One captured frame. `index` is the monotonic sequence number.

    `payload` carries the source-specific image (e.g. a numpy BGR array
    from OpenCV) without importing it here; the detector is the only
    consumer that needs to know the concrete type.
    """

    index: int
    payload: object | None = None


@dataclass(frozen=True)
class GazeTarget:
    """What perception measured about the face, in A1 normalized world
    coordinates: x -1 left / 0 center / +1 right; y -1 down / 0 center /
    +1 up. `confidence` in [0, 1] so behavior can weigh weak detections.
    """

    x: float
    y: float
    confidence: float = 1.0


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