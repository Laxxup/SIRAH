# Stage 8 Perception And Project Readiness

SIRAH is an android robot under prototype development. This repository owns
its eyes subsystem, not the future conversation or whole-robot control stack.

## Scope

1. Commit the verified Stage 8 runtime fixes already in the worktree.
2. Add an optional, real USB-camera perception path using OpenCV and YuNet.
3. Add replay support and tests that do not require a camera or the YuNet model.
4. Complete the P1 project documentation, security/privacy guidance, and third
   party attribution.
5. Document, but do not implement, the future event-driven behavior/LLM layer.

## Perception Design

`OpenCVCameraSource` owns `cv2.VideoCapture` in a dedicated thread and exposes
the newest frame as a `Frame`. It never blocks the asyncio runtime on capture.
Camera construction and startup are explicit and optional; the default runtime
continues to run without perception.

`YuNetFaceDetector` owns an already-local ONNX model. It selects the largest
detected face and maps its center to A1 coordinates: X is -1 on the left and
+1 on the right; Y is -1 at the bottom and +1 at the top. Values are clamped.
It returns `None` for no valid detection. The detector does not smooth, send
commands, or choose servo policy.

The model is never committed or downloaded at import/startup. A versioned
manifest supplies its official URL, SHA-256 and MIT license. An explicit CLI
command downloads it into a configurable model directory and validates the
checksum. A missing or invalid model degrades perception with an actionable
error.

## Integration

The existing `RuntimeApp` pipeline remains the sole wiring point:
`camera -> detector -> GazeBehavior -> SetpointGate -> EyeTransport`.
The CLI gains explicit perception flags. `--fake --eyes` remains a no-hardware
path: it neither imports OpenCV eagerly nor needs a model.

`ReplayCameraSource` fulfills the same camera contract for finite frame/video
sequences. Replay is for deterministic tests and operator debugging; datasets
and captured videos remain ignored from Git.

## Error Handling

Camera startup/read errors degrade `camera`. Model load/detection errors degrade
`behavior` through the existing runtime pipeline. Eye-link failures remain
single-count degradation events. The application continues running unless its
operator stops it.

## Testing

Pure unit tests cover model-manifest validation, checksum failures, coordinate
mapping, largest-face selection, replay EOF and lifecycle errors. Runtime E2E
tests use fakes only. OpenCV tests are isolated and skipped when the optional
extra is absent; CI does not download models or require USB hardware.

## Documentation And Future Intelligence

P1 documentation covers hardware build, calibration, testing, development,
security/privacy and third-party notices. Asset paths are prepared for genuine
laboratory photos and GIFs, without placeholders presented as evidence.

The future LLM design is documentation only: local edge-triggered events,
structured intents, deterministic policy validation, JSONL memory, cooldowns
and shadow mode. It has no direct physical command path and does not add Ollama,
STT or TTS dependencies now.
