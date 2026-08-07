"""SIRAH eyes demo: live preview + physical eyes follow your face left-right.

Detects the largest face with MediaPipe, maps its horizontal position to the
ESP32 eye servo (serial), and centers the gaze when no face is visible.
Throttles detection to keep the preview smooth.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/eyes_demo.py --camera /dev/video2 --serial /dev/ttyUSB0
  PYTHONPATH=src .venv/bin/python scripts/eyes_demo.py --camera /dev/video2 --dry-run

Press 'q' to quit, 'm' to toggle mirror.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

import cv2

from sirah.perception.mediapipe_vision import MediaPipeVision

WIN = "SIRAH eyes - preview + seguimiento (q salir, m mirror)"
DETECT_EVERY = 4
SMOOTHING = 0.30
X_LEFT = 14
X_RIGHT = 90


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def servo_from_face_x(face_x: float, mirror: bool) -> int:
    mirrored = (1.0 - face_x) if mirror else face_x
    norm = clamp(mirrored, 0.0, 1.0)
    return int(round(X_LEFT + norm * (X_RIGHT - X_LEFT)))


def draw_overlay(frame: object, faces: list[object], face_x: float | None, servo_deg: int | None, mirror: bool, fps: float) -> object:
    H, W = frame.shape[:2]
    for face in faces:
        x, y, w, h = (float(v) for v in face.bbox)
        cv2.rectangle(frame, (int(x * W), int(y * H)), (int((x + w) * W), int((y + h) * H)), (0, 255, 60), 2)
    lines = []
    if face_x is None:
        lines.append("sin cara -> CENTER")
    else:
        cx = int(face_x * W)
        cv2.drawMarker(frame, (cx, int(H / 2)), (0, 255, 80), cv2.MARKER_CROSS, 20, 2)
        cv2.line(frame, (cx, 0), (cx, H), (0, 255, 80), 1)
        lines.append(f"cara x={face_x:.2f}")
    if servo_deg is not None:
        lines.append(f"ojo X = {servo_deg} deg")
    lines.append(f"mirror={'on' if mirror else 'off'}  {fps:.0f}fps")
    for i, t in enumerate(lines):
        cv2.putText(frame, t, (10, 22 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 220, 255), 2)
    return frame


class SerialWriter:
    def __init__(self, port: str) -> None:
        self._port = port
        self._writer = None

    async def connect(self) -> None:
        import serial_asyncio  # type: ignore[import-untyped]
        _, self._writer = await serial_asyncio.open_serial_connection(url=self._port, baudrate=115200)

    async def send(self, line: str) -> None:
        if self._writer is None:
            return
        self._writer.write((line + "\n").encode())
        await self._writer.drain()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("eyes_demo")
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default="/dev/video2")
    parser.add_argument("--serial", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mirror", default="true")
    args = parser.parse_args()

    mirror_on = args.mirror.lower() in {"1", "true", "yes", "on"}

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        raise SystemExit(f"no se pudo abrir {args.camera}")

    vision = MediaPipeVision()
    await vision.start()
    log.info("MediaPipe health: %s", await vision.health())

    writer = None
    if args.serial and not args.dry_run:
        writer = SerialWriter(args.serial)
        await writer.connect()
        log.info("serial conectado a %s", args.serial)
    elif args.dry_run:
        log.info("DRY-RUN: sin serial (solo preview + comandos por consola)")

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)

    face_x: float | None = None
    last_faces: list = []
    servo_deg: int | None = None
    frames_since_detection = DETECT_EVERY

    t0 = time.time()
    n = 0
    fps = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            frames_since_detection += 1
            if frames_since_detection >= DETECT_EVERY:
                frames_since_detection = 0
                last_faces = list(await vision.detect(frame))
                if last_faces:
                    largest = max(last_faces, key=lambda f: float(f.bbox[2]) * float(f.bbox[3]))
                    cx = float(largest.bbox[0]) + float(largest.bbox[2]) / 2.0
                    face_x = cx
                    target = servo_from_face_x(face_x, mirror_on)
                    servo_deg = target if servo_deg is None else int(round(servo_deg + (target - servo_deg) * SMOOTHING))
                    cmd = f"X {servo_deg}"
                    if writer:
                        await writer.send(cmd)
                    elif args.dry_run:
                        log.info("cmd %s  (face_x=%.2f)", cmd, face_x)
                else:
                    face_x = None
                    servo_deg = None
                    cmd = "CENTER"
                    if writer:
                        await writer.send(cmd)
                    elif args.dry_run:
                        log.info("cmd %s  (sin cara)", cmd)

            if mirror_on:
                display = cv2.flip(frame, 1)
                draw_x = (1.0 - face_x) if face_x is not None else None
            else:
                display = frame
                draw_x = face_x

            n += 1
            if n % 20 == 0:
                fps = 20 / max(time.time() - t0, 1e-6)
                t0 = time.time()

            cv2.imshow(WIN, draw_overlay(display, last_faces, draw_x, servo_deg, mirror_on, fps))
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("m"):
                mirror_on = not mirror_on
    finally:
        cap.release()
        await vision.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    asyncio.run(main())
