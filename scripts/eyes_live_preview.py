"""Live preview: camera + MediaPipe face detection overlay (visible window).

Proofs the camera turns on and detects a face in real time.
Press 'q' to quit, 'm' to toggle mirror.
"""

from __future__ import annotations

import argparse
import asyncio
import time

import cv2

from sirah.perception.mediapipe_vision import MediaPipeVision

WIN = "SIRAH eyes preview - camera en vivo (q salir)"


def draw(frame: object, faces: object, mirror: bool, fps: float) -> object:
    for face in faces:
        x, y, w, h = (float(v) for v in face.bbox)
        H, W = frame.shape[:2]
        x0, y1_ = int(x * W), int((y + h) * H)
        x1_, y0 = int((x + w) * W), int(y * H)
        cv2.rectangle(frame, (x0, y0), (x1_, y1_), (0, 255, 60), 2)
        cx = int((x + w / 2) * W)
        cv2.drawMarker(frame, (cx, int((y + h / 2) * H)), (0, 180, 255), cv2.MARKER_CROSS, 18, 2)
        cv2.line(frame, (cx, 0), (cx, H), (0, 180, 255), 1)
    cv2.putText(frame, f"caras: {len(faces)}  mirror={'on' if mirror else 'off'}  {fps:.0f} fps",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 220, 255), 2)
    return frame


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default="/dev/video2")
    parser.add_argument("--mirror", default="true")
    args = parser.parse_args()
    mirror_on = args.mirror.lower() in {"1", "true", "yes"}

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        raise SystemExit(f"no se pudo abrir {args.camera}")

    vision = MediaPipeVision()
    await vision.start()
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)

    faces = ()
    t0 = time.time()
    n = 0
    fps = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if mirror_on:
                frame = cv2.flip(frame, 1)
            faces = await vision.detect(frame)
            n += 1
            if n % 30 == 0:
                fps = 30 / max(time.time() - t0, 1e-6)
                t0 = time.time()
            cv2.imshow(WIN, draw(frame, faces, mirror_on, fps))
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
