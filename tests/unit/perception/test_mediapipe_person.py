"""MediaPipePersonDetector adapter tests (M6): person-class filtering,
canonical non-mirrored normalization, provenance, VIDEO timestamps and
failure tolerance — fake detector factory, no mediapipe, no hardware."""

from __future__ import annotations

import numpy as np
import pytest

from sirah.perception.contracts import Frame
from sirah.perception.mediapipe_person import MediaPipePersonDetector


class _Category:
    def __init__(self, category_name: str, score: float) -> None:
        self.category_name = category_name
        self.score = score


class _Box:
    def __init__(self, origin_x: int, origin_y: int, width: int, height: int) -> None:
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.width = width
        self.height = height


class _Detection:
    def __init__(self, category: str, score: float, box: _Box) -> None:
        self.categories = [_Category(category, score)]
        self.bounding_box = box


class FakeResult:
    def __init__(self, detections: list[_Detection]) -> None:
        self.detections = detections


class FakeMediaPipeDetector:
    def __init__(self, results: list[object]) -> None:
        self._results = list(results)
        self.closed = False
        self.calls = 0
        self.timestamps: list[int] = []

    def detect_for_video(self, image: object, timestamp_ms: int) -> object:
        self.timestamps.append(timestamp_ms)
        result = self._results[min(self.calls, len(self._results) - 1)]
        self.calls += 1
        return result

    def close(self) -> None:
        self.closed = True


def _make(model, results: list[object], clock=None) -> MediaPipePersonDetector:
    fake = FakeMediaPipeDetector(results)

    def factory(path) -> FakeMediaPipeDetector:
        assert path == model
        return fake

    detector = MediaPipePersonDetector(
        model, detector_factory=factory, clock=clock or (lambda: 1000.0)
    )
    return detector


@pytest.fixture
def model(tmp_path):
    path = tmp_path / "efficientdet_lite0.tflite"
    path.write_bytes(b"fake")
    return path


def _frame(shape=(32, 32, 3), index=0) -> Frame:
    return Frame(index=index, payload=np.zeros(shape, dtype=np.uint8), captured_at=0.5)


def test_detector_filters_person_class(model):
    results = [
        FakeResult(
            [
                _Detection("person", 0.9, _Box(0, 0, 16, 32)),
                _Detection("car", 0.9, _Box(20, 0, 8, 8)),
            ]
        )
    ]
    detector = _make(model, results)
    detections = detector.detect_persons(_frame())
    assert len(detections) == 1
    d = detections[0]
    # 32x32 frame: box (0,0,16,32) -> normalized (0,0,0.5,1.0)
    assert d.x == 0.0
    assert d.y == 0.0
    assert d.width == 0.5
    assert d.height == 1.0
    assert d.confidence == 0.9


def test_detector_canonical_non_mirrored(model):
    """The adapter NEVER mirrors: mirroring is a presentation-only renderer
    transform (x' = width-1-x)."""
    results = [FakeResult([_Detection("person", 0.8, _Box(4, 0, 8, 8))])]
    detector = _make(model, results)
    detections = detector.detect_persons(_frame())
    # 32x32: origin_x=4 -> normalized x=0.125 (NOT mirrored to 0.875)
    assert detections[0].x == 0.125


def test_detector_provenance(model):
    clock = iter([10.0, 20.0, 30.0, 40.0])  # ts first, then produced_at

    def _clock():
        return next(clock)

    results = [FakeResult([_Detection("person", 0.7, _Box(0, 0, 8, 8))])]
    detector = _make(model, results, clock=_clock)
    detections = detector.detect_persons(_frame(index=12))
    d = detections[0]
    assert d.source_frame_index == 12
    assert d.captured_at == 0.5
    assert d.produced_at == 20.0  # second clock read = inference completion
    assert d.detector == "mediapipe_efficientdet_lite0"


def test_empty_payload_returns_empty(model):
    detector = _make(model, [FakeResult([_Detection("person", 0.9, _Box(0, 0, 8, 8))])])
    assert detector.detect_persons(Frame(index=0, payload=None)) == ()


def test_off_frame_box_is_skipped(model):
    # box fully outside the frame is not an observation; no exception
    results = [FakeResult([_Detection("person", 0.9, _Box(64, 64, 8, 8))])]
    detector = _make(model, results)
    assert detector.detect_persons(_frame()) == ()


def test_invalid_confidence_skipped_not_crashing(model):
    results = [FakeResult([_Detection("person", 9.0, _Box(0, 0, 8, 8))])]
    detector = _make(model, results)
    # PersonDetection rejects confidence>1 at the boundary; skip, don't raise
    assert detector.detect_persons(_frame()) == ()


def test_video_timestamps_monotonic_even_with_stalled_clock(model):
    """VIDEO mode requires monotonically increasing timestamps; the adapter
    guarantees it even when the monotonic clock returns the same value."""
    clock = [10.0]

    def _clock():
        return clock[0]

    fake = FakeMediaPipeDetector(
        [FakeResult([]), FakeResult([]), FakeResult([])]
    )
    detector = MediaPipePersonDetector(
        model, detector_factory=lambda _p: fake, clock=_clock
    )
    detector.detect_persons(_frame())
    detector.detect_persons(_frame())
    detector.detect_persons(_frame())
    assert fake.timestamps[1] > fake.timestamps[0]
    assert fake.timestamps[2] > fake.timestamps[1]


def test_close_releases_detector(model):
    fake = FakeMediaPipeDetector([FakeResult([])])
    detector = MediaPipePersonDetector(model, detector_factory=lambda _p: fake)
    detector.close()
    assert fake.closed


def test_missing_model_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        MediaPipePersonDetector(tmp_path / "missing.tflite")