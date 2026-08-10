from __future__ import annotations

import pytest

from sirah.perception.contracts import Frame
from sirah.perception.yunet import (
    FaceBox,
    YuNetFaceDetector,
    map_face,
    select_largest_face,
)


def test_map_face_converts_bbox_center_to_a1_coordinates():
    target = map_face(FaceBox(0, 0, 20, 20, 0.9), width=100, height=100)
    assert target.x == pytest.approx(-0.8)
    assert target.y == pytest.approx(0.8)
    assert target.confidence == pytest.approx(0.9)


def test_select_largest_face_returns_none_for_no_detections():
    assert select_largest_face([]) is None


def test_select_largest_face_uses_area():
    small = FaceBox(0, 0, 10, 10, 0.9)
    large = FaceBox(50, 50, 20, 20, 0.8)
    assert select_largest_face([small, large]) == large


def test_detector_returns_largest_face_as_target(tmp_path):
    model = tmp_path / "yunet.onnx"
    model.touch()

    class Image:
        shape = (100, 100, 3)

    image = Image()

    class FakeDetector:
        def setInputSize(self, size):
            assert size == (100, 100)

        def detect(self, payload):
            assert payload is image
            return None, [[0, 0, 10, 10, 0, 0, 0, 0, 0, 0.7], [50, 50, 20, 20, 0, 0, 0, 0, 0, 0.9]]

    detector = YuNetFaceDetector(model, detector_factory=lambda _: FakeDetector())
    target = detector.detect(Frame(1, image))
    assert target is not None
    assert (target.x, target.y, target.confidence) == pytest.approx((0.2, -0.2, 0.9))
