#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${SIRAH_MODELS_DIR:-models}"
mkdir -p "$MODEL_DIR"

curl --fail --location --retry 3 \
  -o "$MODEL_DIR/face_landmarker.task" \
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
curl --fail --location --retry 3 \
  -o "$MODEL_DIR/hand_landmarker.task" \
  "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"

ls -lh "$MODEL_DIR"/*.task
