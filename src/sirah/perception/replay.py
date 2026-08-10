"""Deterministic in-memory camera source for offline replay."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from sirah.perception.contracts import Frame


class ReplayCameraSource:
    """Expose a finite payload sequence through the CameraSource contract."""

    def __init__(self, payloads: Iterable[object]) -> None:
        self._payloads: Iterator[object] = iter(payloads)
        self._index = 0
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def next_frame(self) -> Frame | None:
        if not self._running:
            return None
        try:
            payload = next(self._payloads)
        except StopIteration:
            return None
        frame = Frame(index=self._index, payload=payload)
        self._index += 1
        return frame

    async def stop(self) -> None:
        self._running = False


class JsonlReplayCameraSource(ReplayCameraSource):
    """Replay JSONL records with image paths resolved beside the manifest."""

    def __init__(self, manifest: Path) -> None:
        records: list[object] = []
        for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict) or not isinstance(record.get("image"), str):
                raise TypeError(f"{manifest}:{line_number}: record requires string 'image'")
            record["image"] = manifest.parent / record["image"]
            records.append(record)
        super().__init__(records)


class OpenCVJsonlReplayCameraSource(JsonlReplayCameraSource):
    """Decode each JSONL image path before exposing it as a frame payload."""

    def __init__(
        self, manifest: Path, *, image_loader: Callable[[Path], object] | None = None
    ) -> None:
        super().__init__(manifest)
        self._image_loader = image_loader or _opencv_image_loader

    async def next_frame(self) -> Frame | None:
        frame = await super().next_frame()
        if frame is None:
            return None
        assert isinstance(frame.payload, dict)
        image = frame.payload["image"]
        assert isinstance(image, Path)
        payload = self._image_loader(image)
        if payload is None:
            raise OSError(f"cannot load replay image {image}")
        return Frame(index=frame.index, payload=payload)


class VideoReplayCameraSource:
    """Optional OpenCV video-file source for real replay datasets."""

    def __init__(
        self, video: Path, *, capture_factory: Callable[[Path], object] | None = None
    ) -> None:
        self._video = video
        self._capture_factory = capture_factory
        self._capture: object | None = None
        self._index = 0

    async def start(self) -> None:
        capture = (self._capture_factory or _opencv_video_capture)(self._video)
        if not capture.isOpened():  # type: ignore[attr-defined]
            raise OSError(f"cannot open replay video {self._video}")
        self._capture = capture

    async def next_frame(self) -> Frame | None:
        if self._capture is None:
            return None
        ok, payload = self._capture.read()  # type: ignore[attr-defined]
        if not ok:
            return None
        frame = Frame(index=self._index, payload=payload)
        self._index += 1
        return frame

    async def stop(self) -> None:
        if self._capture is not None:
            self._capture.release()  # type: ignore[attr-defined]
        self._capture = None


def _opencv_video_capture(video: Path) -> object:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError('install perception support: pip install -e ".[perception]"') from exc
    return cv2.VideoCapture(str(video))


def _opencv_image_loader(image: Path) -> object:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError('install perception support: pip install -e ".[perception]"') from exc
    return cv2.imread(str(image))
