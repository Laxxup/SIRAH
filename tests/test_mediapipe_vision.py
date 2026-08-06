"""Deterministic tests for MediaPipe vision helpers."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from sirah.perception.mediapipe_vision import (
    MediaPipeVision,
    count_extended_fingers,
    smile_score_from_blendshapes,
)


def _landmarks(*points: tuple[float, float]) -> list[SimpleNamespace]:
    values = [SimpleNamespace(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    for index, (x, y) in enumerate(points):
        values[index] = SimpleNamespace(x=x, y=y, z=0.0)
    return values


def test_count_extended_fingers_counts_all_five() -> None:
    points = [(0.5, 0.8)] * 21
    points[4] = (0.2, 0.35)
    points[3] = (0.35, 0.5)
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        points[tip] = (0.5, 0.2)
        points[pip] = (0.5, 0.4)

    assert count_extended_fingers(_landmarks(*points)) == (True, True, True, True, True)


def test_count_extended_fingers_counts_closed_hand_as_zero() -> None:
    points = [(0.5, 0.8)] * 21
    points[4] = (0.46, 0.62)
    points[3] = (0.44, 0.54)
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        points[tip] = (0.5, 0.62)
        points[pip] = (0.5, 0.45)

    assert count_extended_fingers(_landmarks(*points)) == (
        False,
        False,
        False,
        False,
        False,
    )


def test_smile_score_uses_both_face_blendshapes() -> None:
    categories = [
        SimpleNamespace(category_name="mouthSmileLeft", score=0.8),
        SimpleNamespace(category_name="mouthSmileRight", score=0.6),
    ]

    assert smile_score_from_blendshapes(categories) == 0.7


def test_model_paths_accept_home_models_directory() -> None:
    vision = MediaPipeVision(model_dir="/home/laxxup/models")

    assert vision.model_dir.name == "models"


def test_face_result_keeps_sorted_people_and_blendshape_smiles() -> None:
    def face_landmarks(x1: float, x2: float) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(x=x1 if index % 2 else x2, y=0.1 + index % 3 * 0.1, z=0.0)
            for index in range(21)
        ]

    class FakeFaceLandmarker:
        def detect(self, image):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                face_landmarks=[face_landmarks(0.1, 0.3), face_landmarks(0.6, 0.8)],
                face_blendshapes=[
                    [
                        SimpleNamespace(category_name="mouthSmileLeft", score=0.8),
                        SimpleNamespace(category_name="mouthSmileRight", score=0.8),
                    ],
                    [
                        SimpleNamespace(category_name="mouthSmileLeft", score=0.1),
                        SimpleNamespace(category_name="mouthSmileRight", score=0.1),
                    ],
                ],
            )

    vision = MediaPipeVision(model_dir="/tmp/no-models")
    vision._face_landmarker = FakeFaceLandmarker()
    vision._mediapipe_started = True
    vision._to_image = lambda frame: None  # type: ignore[method-assign]
    frame = np.zeros((240, 400, 3), dtype=np.uint8)
    frame[72:144, 20:140] = (60, 160, 60)
    frame[72:144, 240:360] = (40, 120, 220)

    detections, context = vision._face_data(frame)

    assert len(detections) == 2
    assert [face.dominant_color for face in context.face_contexts] == [
        "verde",
        "naranja",
    ]
    assert [face.smiling for face in context.face_contexts] == [True, False]
    assert [face.smile_source for face in context.face_contexts] == [
        "blendshape",
        "blendshape",
    ]


def test_hand_result_counts_fingers_and_keeps_handedness() -> None:
    points = [(0.5, 0.8)] * 21
    points[4] = (0.2, 0.35)
    points[3] = (0.35, 0.5)
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        points[tip] = (0.5, 0.2)
        points[pip] = (0.5, 0.4)

    class FakeHandLandmarker:
        def detect(self, image):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                hand_landmarks=[_landmarks(*points)],
                handedness=[[SimpleNamespace(category_name="Left")]],
            )

    vision = MediaPipeVision(model_dir="/tmp/no-models")
    vision._hand_landmarker = FakeHandLandmarker()
    vision._to_image = lambda frame: None  # type: ignore[method-assign]

    context = vision._hand_data(np.zeros((240, 400, 3), dtype=np.uint8))

    assert context.hand_count == 1
    assert context.hands[0].handedness == "Left"
    assert context.hands[0].finger_count == 5
    assert context.hands[0].bbox == (0.2, 0.2, 0.3, 0.6)
