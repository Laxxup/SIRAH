from __future__ import annotations

import asyncio

from sirah.perception.opencv_camera import OpenCVCameraSource


class FakeCapture:
    def __init__(self) -> None:
        self.released = False
        self.reads = 0

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple[bool, object]:
        self.reads += 1
        return True, {"frame": self.reads}

    def release(self) -> None:
        self.released = True


async def test_camera_returns_latest_frame_and_releases_capture():
    capture = FakeCapture()
    source = OpenCVCameraSource(0, capture_factory=lambda _: capture)

    await source.start()
    for _ in range(20):
        frame = await source.next_frame()
        if frame is not None:
            break
        await asyncio.sleep(0.001)

    assert frame is not None
    assert frame.payload is not None
    await source.stop()
    assert capture.released
