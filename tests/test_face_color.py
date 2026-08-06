"""Regression tests for stable visual classification."""

from __future__ import annotations

import numpy as np

import sirah.autonomy.vision_loop as vision_loop
import sirah.perception.face_detector as face_detector
from sirah.autonomy.vision_loop import VisionLoop
from sirah.perception.face_detector import VisualContext
from sirah.perception.mediapipe_vision import HandVisualContext, MediaPipeVision


def test_classify_color_rejects_warm_gray_as_green() -> None:
    assert face_detector._classify_color((140, 142, 138)) == "gris"
    assert face_detector._classify_color((98, 100, 96)) == "gris oscuro"


def test_classify_color_uses_hue_for_saturated_bgr_values() -> None:
    assert face_detector._classify_color((60, 160, 60)) == "verde"
    assert face_detector._classify_color((40, 120, 220)) == "naranja"
    assert face_detector._classify_color((220, 40, 40)) == "azul"


def test_classify_color_handles_black_and_white() -> None:
    assert face_detector._classify_color((10, 10, 10)) == "negro"
    assert face_detector._classify_color((255, 255, 255)) == "blanco"


def test_modal_prefers_most_frequent_value() -> None:
    assert vision_loop._modal(["gris", "verde", "gris"]) == "gris"


def test_prompts_do_not_invent_unseen_hands_or_objects() -> None:
    assert "No afirmes manos, dedos" in vision_loop.GREET_PROMPT
    assert "No afirmes manos, dedos" in vision_loop.IDLE_PROMPT


def test_smile_state_requires_two_consecutive_confirmations() -> None:
    loop = VisionLoop(orchestrator=None)  # type: ignore[arg-type]

    assert loop._stabilize_context(VisualContext(1, smiling=False)).smiling is False
    assert loop._stabilize_context(VisualContext(1, smiling=True)).smiling is False
    assert loop._stabilize_context(VisualContext(1, smiling=True)).smiling is True
    assert loop._stabilize_context(VisualContext(1, smiling=False)).smiling is True
    assert loop._stabilize_context(VisualContext(1, smiling=False)).smiling is False


def test_each_face_smile_state_requires_two_confirmations() -> None:
    loop = VisionLoop(orchestrator=None)  # type: ignore[arg-type]
    neutral = VisualContext(
        face_count=1,
        face_contexts=(face_detector.FaceVisualContext(smiling=False),),
    )
    smiling = VisualContext(
        face_count=1,
        face_contexts=(face_detector.FaceVisualContext(smiling=True),),
    )

    assert loop._stabilize_context(neutral).face_contexts[0].smiling is False
    assert loop._stabilize_context(smiling).face_contexts[0].smiling is False
    assert loop._stabilize_context(smiling).face_contexts[0].smiling is True


def test_blendshape_expression_uses_dead_zone_without_extra_confirmation() -> None:
    loop = VisionLoop(orchestrator=None)  # type: ignore[arg-type]
    neutral = VisualContext(
        face_count=1,
        face_contexts=(face_detector.FaceVisualContext(
            smiling=False,
            smile_score=0.20,
            smile_source="blendshape",
        ),),
    )
    smiling = VisualContext(
        face_count=1,
        face_contexts=(face_detector.FaceVisualContext(
            smiling=True,
            smile_score=0.50,
            smile_source="blendshape",
        ),),
    )
    ambiguous = VisualContext(
        face_count=1,
        face_contexts=(face_detector.FaceVisualContext(
            smiling=False,
            smile_score=0.35,
            smile_source="blendshape",
        ),),
    )

    assert loop._stabilize_context(neutral).face_contexts[0].smiling is False
    assert loop._stabilize_context(smiling).face_contexts[0].smiling is True
    assert loop._stabilize_context(ambiguous).face_contexts[0].smiling is True


def test_face_count_waits_for_two_confirmations() -> None:
    loop = VisionLoop(orchestrator=None)  # type: ignore[arg-type]
    one = VisualContext(face_count=1)
    two = VisualContext(face_count=2)

    assert loop._stabilize_context(one).face_count == 1
    assert loop._stabilize_context(two).face_count == 1
    assert loop._stabilize_context(two).face_count == 2


def test_expression_change_hint_is_consumed_once() -> None:
    loop = VisionLoop(orchestrator=None)  # type: ignore[arg-type]

    loop._stabilize_context(VisualContext(face_count=1, smiling=False))
    loop._stabilize_context(VisualContext(face_count=1, smiling=True))
    loop._stabilize_context(VisualContext(face_count=1, smiling=True))

    changed_hint = loop._build_visual_hint(VisualContext(face_count=1, smiling=True), [])
    stable_hint = loop._build_visual_hint(VisualContext(face_count=1, smiling=True), [])

    assert "Cambió su expresión" in changed_hint
    assert "Cambió su expresión" not in stable_hint


async def test_analyze_keeps_visual_data_for_each_face() -> None:
    class FaceCascade:
        def detectMultiScale(self, image, **kwargs):  # type: ignore[no-untyped-def]  # noqa: N802
            return np.array([[20, 20, 100, 100], [220, 20, 100, 100]])

    class SmileCascade:
        def detectMultiScale(self, image, **kwargs):  # type: ignore[no-untyped-def]  # noqa: N802
            return np.array([[20, 10, 40, 15]])

    detector = face_detector.FaceDetector()
    detector._cascade = FaceCascade()
    detector._smile_cascade = SmileCascade()
    detector._initialised = True
    frame = np.zeros((240, 400, 3), dtype=np.uint8)
    frame[120:220, 0:160] = (60, 160, 60)
    frame[120:220, 180:360] = (40, 120, 220)

    detections = await detector.detect(frame)
    context = await detector.analyze(frame)

    assert len(detections) == 2
    assert context.face_count == 2
    assert len(context.face_contexts) == 2
    assert [face.dominant_color for face in context.face_contexts] == [
        "verde",
        "naranja",
    ]
    assert [face.smiling for face in context.face_contexts] == [True, True]


async def test_analyze_refreshes_hands_on_each_tick() -> None:
    class HandDetector:
        def __init__(self) -> None:
            self.hand_ticks = 0

        async def detect(self, frame):  # type: ignore[no-untyped-def]
            return ()

        async def analyze(self, frame):  # type: ignore[no-untyped-def]
            return VisualContext(face_count=0)

        async def analyze_hands(self, frame):  # type: ignore[no-untyped-def]
            self.hand_ticks += 1
            return HandVisualContext()

    detector = HandDetector()
    loop = VisionLoop(orchestrator=None, face_detector=detector)  # type: ignore[arg-type]
    loop._latest_frame = np.zeros((10, 10, 3), dtype=np.uint8)

    await loop._analyze_tick()
    await loop._analyze_tick()

    assert detector.hand_ticks == 2


async def test_refresh_context_updates_faces_and_hands_from_current_frame() -> None:
    class FreshDetector:
        async def detect(self, frame):  # type: ignore[no-untyped-def]
            return ("face",)

        async def analyze(self, frame):  # type: ignore[no-untyped-def]
            return VisualContext(face_count=1)

        async def analyze_hands(self, frame):  # type: ignore[no-untyped-def]
            return HandVisualContext()

    loop = VisionLoop(orchestrator=None, face_detector=FreshDetector())  # type: ignore[arg-type]
    loop._latest_frame = np.zeros((10, 10, 3), dtype=np.uint8)

    context = await loop.refresh_context()

    assert context.face_count == 1
    assert loop._latest_faces == ("face",)


async def test_face_analysis_cadence_is_configurable() -> None:
    class CountingDetector:
        def __init__(self) -> None:
            self.face_ticks = 0

        async def detect(self, frame):  # type: ignore[no-untyped-def]
            self.face_ticks += 1
            return ()

        async def analyze(self, frame):  # type: ignore[no-untyped-def]
            return VisualContext(face_count=0)

        async def analyze_hands(self, frame):  # type: ignore[no-untyped-def]
            return HandVisualContext()

    detector = CountingDetector()
    loop = VisionLoop(
        orchestrator=None,
        face_detector=detector,
        face_analyze_every=3,
    )  # type: ignore[arg-type]
    loop._latest_frame = np.zeros((10, 10, 3), dtype=np.uint8)

    await loop._analyze_tick()
    await loop._analyze_tick()
    await loop._analyze_tick()

    assert detector.face_ticks == 1


def test_torso_roi_falls_back_to_visible_bottom_band() -> None:
    vision = MediaPipeVision()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    bbox = vision._torso_bbox(frame, (30, 70, 30, 30))

    assert bbox[1] < bbox[3]
    assert bbox[3] == 100


def test_visual_hint_names_people_and_distinct_clothing_colors() -> None:
    loop = VisionLoop(orchestrator=None)  # type: ignore[arg-type]
    context = VisualContext(
        face_count=2,
        dominant_color="varios",
        face_contexts=(
            face_detector.FaceVisualContext(dominant_color="verde", smiling=True),
            face_detector.FaceVisualContext(dominant_color="naranja", smiling=True),
        ),
    )

    hint = loop._build_visual_hint(context, [])

    assert "Contexto visual actual y completo" in hint
    assert "2 personas" in hint
    assert "2 colores" in hint
    assert "verde" in hint
    assert "naranja" in hint
    assert hint.count("sonriendo") == 2

    loop._latest_visual_ctx = context
    description = loop.vision_description
    assert description.startswith("2 personas;")
    assert "persona 1: ropa verde, sonriendo" in description
    assert "persona 2: ropa naranja, sonriendo" in description

    named_hint = loop._build_visual_hint(context, ["Ana", "Beto"])
    assert "Persona 1 se llama 'Ana'" in named_hint
    assert "Persona 2 se llama 'Beto'" in named_hint
