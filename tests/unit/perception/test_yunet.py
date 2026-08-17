from __future__ import annotations

from pathlib import Path

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


def test_detection_parameters_are_forwarded_to_opencv_create(monkeypatch, tmp_path):
    """score/nms/top_k reach the real FaceDetectorYN.create call (via the
    default factory), matching the OpenCV Zoo YuNet class parameters."""
    import sirah.perception.yunet as yunet_mod

    model = tmp_path / "yunet.onnx"
    model.touch()

    seen: dict[str, object] = {}

    def fake_detector(
        model_path: Path, *, score_threshold: float, nms_threshold: float, top_k: int
    ) -> object:
        assert model_path == model
        seen["score_threshold"] = score_threshold
        seen["nms_threshold"] = nms_threshold
        seen["top_k"] = top_k
        return object()

    monkeypatch.setattr(yunet_mod, "_opencv_detector", fake_detector)
    YuNetFaceDetector(
        model,
        score_threshold=0.7,
        nms_threshold=0.4,
        top_k=100,
    )
    assert seen == {"score_threshold": 0.7, "nms_threshold": 0.4, "top_k": 100}


def test_default_detection_parameters_match_zoo_library(monkeypatch, tmp_path):
    """Defaults are the OpenCV Zoo YuNet class values (score 0.6, nms 0.3)."""
    import sirah.perception.yunet as yunet_mod

    model = tmp_path / "yunet.onnx"
    model.touch()

    seen: dict[str, object] = {}

    def fake_detector(
        model_path: Path, *, score_threshold: float, nms_threshold: float, top_k: int
    ) -> object:
        seen.update(
            score_threshold=score_threshold,
            nms_threshold=nms_threshold,
            top_k=top_k,
        )
        return object()

    monkeypatch.setattr(yunet_mod, "_opencv_detector", fake_detector)
    YuNetFaceDetector(model)
    assert seen == {"score_threshold": 0.6, "nms_threshold": 0.3, "top_k": 5000}


def test_detector_reports_every_face_via_detect_many(tmp_path):
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
    faces = detector.detect_many(Frame(1, image))
    assert len(faces) == 2
    assert (faces[0].x, faces[0].y, faces[0].confidence) == pytest.approx((-0.9, 0.9, 0.7))
    assert (faces[1].x, faces[1].y, faces[1].confidence) == pytest.approx((0.2, -0.2, 0.9))
