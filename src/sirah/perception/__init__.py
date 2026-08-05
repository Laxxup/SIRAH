"""Perception layer — visual sensing via MediaPipe + OpenCV."""

from __future__ import annotations

__all__ = [
    "PerceptionPort",
    "FaceDetector",
    "PoseDetector",
    "WebcamCapture",
    "SimulatedPerception",
]

from sirah.perception.port import PerceptionPort
from sirah.perception.face_detector import FaceDetector
from sirah.perception.pose_detector import PoseDetector
from sirah.perception.webcam import WebcamCapture
from sirah.perception.simulated import SimulatedPerception
