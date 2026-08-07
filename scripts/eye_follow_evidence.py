"""Eye-following evidence: detect face with MediaPipe, drive ESP32 eye-x over serial.

Dry-run mode prints commands without sending anything (no serial dependency).
Pass --serial /dev/ttyUSB0 to actually command the servos.

Frames and logs land in /tmp/sirah-evidence/.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import math
import os
import time
from pathlib import Path

import cv2

from sirah.perception.mediapipe_vision import MediaPipeVision

EVIDENCE_DIR = Path("/tmp/sirah-evidence")
LOG_FIELDS = ["t", "frame", "face_x", "servo_100", "servo_deg", "autonomy", "yaw", "pitch"]
MIRROR_DEFAULT = True
DEFAULT_CAMERA = "/dev/video2"
SMOOTHING = 0.25


def normalized_center(face: object) -> tuple[float, float] | None:
    bbox = getattr(face, "bbox", None)
    if not bbox or len(bbox) != 4:
        return None
    x, y, w, h = (float(v) for v in bbox)
    return x + w / 2.0, y + h / 2.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(current: float | None, target: float, factor: float) -> float:
    if current is None:
        return target
    return current + (target - current) * factor


def draw_overlay(
    frame: object,
    faces: list[object] | tuple[object, ...],
    face_x: float | None,
    servo_100: float | None,
    mirror_on: bool,
) -> object:
    height, width = frame.shape[:2]

    for face in faces:
        x, y, w, h = (float(v) for v in face.bbox)
        x0 = int(x * width)
        y0 = int(y * height)
        x1 = int((x + w) * width)
        y1 = int((y + h) * height)
        cv2.rectangle(frame, (x0, y0), (x1, y1), (0, 255, 60), 2)

    text = []
    if face_x is None:
        text.append("no face -> CENTER")
    else:
        cx = int(face_x * width)
        cv2.drawMarker(frame, (cx, int(height / 2)), (0, 255, 50), cv2.MARKER_CROSS, 24, 2)
        cv2.line(frame, (cx, 0), (cx, height), (0, 255, 50), 1)
        text.append(f"face_x={face_x:.2f}")
    if servo_100 is not None:
        text.append(f"X={servo_100:.0f} ({servo_deg(servo_100)})")
    text.append(f"mirror={'on' if mirror_on else 'off'}")
    for i, line in enumerate(text):
        cv2.putText(frame, line, (10, 20 + i * 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 200, 255), 2)
    return frame


def servo_deg(value100: float) -> int:
    return int(round(14.0 + (value100 / 100.0) * (90.0 - 14.0)))


class SerialWriter:
    def __init__(self, port: str) -> None:
        self._port = port
        self._writer = None

    async def connect(self) -> None:
        import serial_asyncio  # type: ignore[import-untyped]

        reader, self._writer = await serial_asyncio.open_serial_connection(url=self._port, baudrate=115200)
        reader  # unused; keep referenced

    async def send(self, line: str) -> None:
        if self._writer is None:
            return
        self._writer.write((line + "\n").encode())
        await self._writer.drain()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("eye_evidence")
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default=DEFAULT_CAMERA)
    parser.add_argument("--serial", default=None)
    parser.add_argument("--mirror", default=str(MIRROR_DEFAULT))
    parser.add_argument("--no-serial", action="store_true")
    parser.add_argument("--frames", type=int, default=200)
    parser.add_argument("--annotate-every", type=int, default=10)
    args = parser.parse_args()

    mirror_on = args.mirror.lower() in {"1", "true", "yes", "on"}
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        raise SystemExit(f"no se pudo abrir la camara {args.camera}")

    vision = MediaPipeVision()
    await vision.start()
    if not await vision.health():
        logger.warning("MediaPipe health false; las caras se rastrearan si los modelos existen")

    writer = None
    if args.serial and not args.no_serial:
        writer = SerialWriter(args.serial)
        await writer.connect()
        logger.info("serial conectado a %s", args.serial)

    log_path = EVIDENCE_DIR / "eye_log.csv"
    with open(log_path, "w", newline="") as csvfile:
        writer_csv = csv.DictWriter(csvfile, fieldnames=LOG_FIELDS)
        writer_csv.writeheader()

        servo_100: float | None = None
        autonomy = 1
        last_face_x: float | None = None
        saved = 0

        try:
            for frame_index in range(args.frames):
                ok, frame = cap.read()
                if not ok:
                    continue

                faces = await vision.detect(frame)
                face_center = None
                if faces:
                    largest = max(faces, key=lambda f: float(f.bbox[2]) * float(f.bbox[3]))
                    center = normalized_center(largest)
                    if center is not None:
                        face_center = center[0]
                        last_face_x = center[0]

                if face_center is not None:
                    autonomy = 0
                    mirrored = (1.0 - face_center) if mirror_on else face_center
                    target = clamp(mirrored, 0.0, 1.0) * 100.0
                    servo_100 = lerp(servo_100, target, SMOOTHING)
                    command = f"X {servo_100:.0f}"
                    autonomy_label = "track"
                else:
                    servo_100 = None
                    command = "CENTER"
                    autonomy_label = "center"

                writer_csv.writerow(
                    {
                        "t": f"{time.time():.3f}",
                        "frame": frame_index,
                        "face_x": "" if face_center is None else f"{face_center:.4f}",
                        "servo_100": "" if servo_100 is None else f"{servo_100:.2f}",
                        "servo_deg": "" if servo_100 is None else str(servo_deg(servo_100)),
                        "autonomy": autonomy_label,
                        "yaw": "",
                        "pitch": "",
                    }
                )

                if writer is not None:
                    await writer.send(command)

                if frame_index % args.annotate_every == 0:
                    annotated = draw_overlay(frame.copy(), faces, face_center, servo_100, mirror_on)
                    out = EVIDENCE_DIR / f"frame_{frame_index:04d}.jpg"
                    cv2.imwrite(str(out), annotated)
                    saved += 1
                    logger.info(
                        "frame %d | %s -> %s",
                        frame_index,
                        f"face_x={face_center:.2f}" if face_center is not None else "no face",
                        command,
                    )
        finally:
            cap.release()
            await vision.stop()

    logger.info("evidencia guardada en %s (%d frames, log %s)", EVIDENCE_DIR, saved, log_path)


if __name__ == "__main__":
    asyncio.run(main())
