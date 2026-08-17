"""Explicit, checksum-verified installers for optional perception models."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"

GESTURE_FILENAME = "gesture_recognizer.task"
GESTURE_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
    "gesture_recognizer/float16/1/gesture_recognizer.task"
)
GESTURE_SHA256 = "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482"


def install_yunet(destination: Path) -> Path:
    """Download the OpenCV Zoo YuNet ONNX model after verifying its digest."""
    payload = urlopen(YUNET_URL, timeout=30).read()
    if sha256(payload).hexdigest() != YUNET_SHA256:
        raise ValueError("YuNet model SHA-256 mismatch")
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / YUNET_FILENAME
    path.write_bytes(payload)
    return path


def install_gesture(destination: Path) -> Path:
    """Download the MediaPipe GestureRecognizer task model after verifying
    its digest (float16 variant, ~8 MiB, for the `gesture` extra)."""
    payload = urlopen(GESTURE_URL, timeout=30).read()
    if sha256(payload).hexdigest() != GESTURE_SHA256:
        raise ValueError("gesture model SHA-256 mismatch")
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / GESTURE_FILENAME
    path.write_bytes(payload)
    return path
