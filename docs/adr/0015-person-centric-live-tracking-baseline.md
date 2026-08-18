# ADR-0015 — M6 person-centric live tracking baseline

Status: accepted (M6 baseline)
Date: 2026-08

## Context

M6 must maintain a fresh, conservative, temporally coherent representation
of the people a single fixed camera observes — without identity, biometrics,
or 3D. The decision record covers detector and tracker selection for both the
current Intel x86 development machine and the future Raspberry Pi 4B (8GB)
target.

Constraints that shaped this decision:

- project license is Apache-2.0; nothing AGPL/copyleft may enter;
- zero new runtime dependencies preferred; `mediapipe` is already a
  dependency (gesture extra) and is physically validated on this machine;
- detection/tracking must never own the camera (one media owner — the
  FrameBroker);
- latest-frame semantics: a slow detector drops frames, never queues them;
- track_id is a session-local temporary identity, never a human identity;
- VIDEO mode (not LIVE_STREAM) so FrameBroker keeps control of freshness —
  unchanged from the GestureRecognizer decision.

## Candidate person detectors

| Candidate | Runtime | Code license | Model license | x86 | RPi4 | Notes |
|---|---|---|---|---|---|---|
| MediaPipe ObjectDetector (EfficientDet-Lite0, 320x320) | mediapipe 1.0.1 (installed) | Apache-2.0 | Apache-2.0 (COCO-trained, 80 classes) | measured ~50 ms/frame (p50) on 640x480 | feasible (TFLite/XNNPACK; int8 variant for ARM) | zero new deps; person class filtered at adapter |
| YOLOX-nano (ONNX) | ONNX Runtime | Apache-2.0 | Apache-2.0 (Megvii official weights) | ~few ms (0.91M params, 1.08 GFLOPs, 416px) | feasible (ONNX Runtime ARM) | onnxruntime not installed in current env; adds a dependency; NMS + export preprocessing needed |
| OpenVINO person-detection-0200 | OpenVINO | Apache-2.0 | Apache-2.0 (Open Model Zoo) | fast on Intel | not a realistic RPi target | heavy dependency; x86-only value |
| Ultralytics YOLO (v8/v11) | torch/ultralytics | AGPL-3.0 | AGPL-3.0 | fast | heavy | EXCLUDED — license incompatible without explicit audit; not introduced |

### Why EfficientDet-Lite0 won the baseline
- zero new dependencies (mediapipe already present and validated);
- matches the existing `mediapipe_gesture` adapter pattern exactly
  (BaseOptions + mp.Image + monotonic VIDEO timestamps);
- Apache-2.0 code and model, single downloadable `.tflite` (~6.9 MiB)
  with a verified SHA-256;
- measured ~50 ms/frame on the x86 dev machine → ~20 Hz inference rate,
  comfortably within the "fresh ~8 Hz" floor the mission allows, leaving
  CPU headroom for YuNet + gesture + viewer;
- the general 80-class model costs little: Lite0 is already near the
  "dedicated person detector" size class. A person-only variant would save
  a bounded fraction; the `PersonDetector` protocol keeps that swap cheap
  if a future benchmark demands it. YOLOX-nano is documented as the
  fallback candidate (would require adding onnxruntime + NMS glue).

## Candidate trackers

| Candidate | License | Deps | ReID | Measured/adopted |
|---|---|---|---|---|
| ByteTrack (BYTE association) | MIT | torch (reference impl) | none | association logic adopted as a pure-Python greedy IoU tracker |
| BoT-SORT / BoT-SORT-ReID | MIT | torch + FastReID + faiss | optional | REJECTED for M6: heavy deps; ReID raises IDF1 ~79.5→80.2 on MOT17 (marginal) at large CPU cost |
| OpenCV legacy trackers (KCF/CSRT) | Apache-2.0 | opencv | none | rejected: single-object, unmaintained, no clean MOT manager |

### ReID decision
Off. ByteTrack's core claim — spatial (IoU) association of every detection
box is usually sufficient on a fixed camera — matches SIRAH's target. ReID
adds an embedding network per person-crop and only pays off under long
occlusions or camera motion. Enable ReID later only if a measured benchmark
shows unacceptable ID switches. The tracker is a pure Python class; a ReID
adapter could be layered without changing scene semantics.

### Tracker implementation
`GreedyIoUTracker` in `person_tracker.py`: ByteTrack-style two-stage
association (high-score detections first, then low-score recovery),
greedy IoU matching (deterministic; Hungarian unnecessary for ≤ tens of
boxes), per-track lost-buffer, tentative→confirmed→temporarily_lost→expired
lifecycle, optional normalized-space velocity estimate. Zero dependencies;
fully deterministic and unit-testable.

## Data model / semantics

- `PersonDetection`: canonical NON-mirrored normalized bbox
  (x, y, width, height), confidence, `source_frame_index`, `captured_at`,
  `produced_at`, detector provenance.
- `PersonTrack`: `track_id` (session-local int), lifecycle, latest bbox,
  confidence, first_seen/last_seen, last_source_frame_index, velocity,
  provenance. NEVER a human identity.
- `ObservedScene`: the camera-centric description (tracks + observed_at +
  source_frame_index + freshness), distinct from a global WorldModel.
  States: OBSERVED NOW / RECENTLY OBSERVED (temporarily_lost) / STALE /
  UNKNOWN. Nothing outside the camera FOV is inferred; no metric depth;
  2D normalized coordinates only.
- Temporal provenance: every observation retains source frame index +
  capture timestamp + completion timestamp + age; fusion of person/face/
  hand observations from different source frames is FORBIDDEN without proof
  of correspondence (owner = unknown is a valid result).

## Model file

- name: `efficientdet_lite0.tflite` (MediaPipe float16 v1)
- source: `https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/1/efficientdet_lite0.tflite`
- license: Apache-2.0
- sha256: `4b59100025bea1235a84c1038879a6cccc9f6c49f5e41144e91e74d99e780993`
- input: 320x320 RGB; internal preprocessing color/order handled by MediaPipe
- cache path: `models/person/efficientdet_lite0.tflite` (installer:
  `sirah-models person`)
- no silent download; tests never require the model or Internet.

## Deferred (NOT in M6)

Wave, gestures-from-track, person↔face ownership, object scene, VLM, ReID,
OpenVINO acceleration, Raspberry Pi benchmarking (documented only; physical
RPi acceptance is out of scope until run there).