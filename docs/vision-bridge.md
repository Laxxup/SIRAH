# Vision Bridge

Vision usa una frontera C++ estrecha compatible con OpenCV 4 y OpenCV 5:

`Go -> internal/vision -> C API -> OpenCV -> V4L2 USB camera / YuNet`

The native side contains only camera lifecycle, frame capture, YuNet inference,
raw bounding-box extraction, and basic error reporting. Target selection,
tracking, smoothing, hysteresis, normalization, Motion, Firmware, Agent, and
memory remain outside the bridge.

## API

`internal/vision/bridge.h` exposes an opaque `vision_handle_t` and flat
`vision_face_detection_t` values. Go owns the handle reference and must call
`Close`. C++ owns the persistent `VideoCapture`, detector, and current frame.
`vision_detect` writes into a caller-owned Go slice only during the call; C++
does not retain that pointer.

The sequence is `Open`, repeated `Read` then `Detect`, and `Close`.

`Read` retries up to three times with a 50 ms delay when a native capture read
fails. The current frame is never reused after a failed read. After three
consecutive failures the error is returned to the caller.

The manual command accepts `--preview` to show a native OpenCV debug window.
The preview receives only the current raw detections and draws their rectangles;
it does not select, track, smooth, normalize, or otherwise interpret them. Press
`q`, `Esc`, or closing the window stops the preview command. The preview requires a graphical
environment. With `--debug`, the command also prints `read_ms`, `detect_ms`,
`preview_ms`, and `loop_ms` for each cycle.

When preview is enabled, the command locks its main goroutine to one OS thread.
`imshow`, `waitKey(1)`, and window destruction therefore run on that same thread.
SIGINT and SIGTERM cancel the loop through `signal.NotifyContext`; cleanup then
destroys HighGUI windows before releasing the detector and camera.

## Build

Required packages:

- OpenCV 4 development headers and libraries, including `core`, `objdetect`, and `videoio`.
- `pkg-config`.
- A C++11 compiler and Go with CGO enabled.
- Linux V4L2 support and permissions for the USB camera.

The bridge uses `pkg-config opencv4` by default; it does not hardcode include
or library paths. On Raspberry Pi OS ARM64, install the equivalent OpenCV 4
development package built for ARM64 and ensure `pkg-config --modversion opencv4`
works. The bridge API used here exists in both major versions:

```sh
make check-opencv
```

Ese target ejecuta tests, race detector, vet y build con OpenCV 4, la ruta por
defecto y la variante actualmente cubierta por CI. Para omitir Vision y CGO usa
`make test-headless` y `make vet-headless`.

OpenCV 5 es opt-in mediante el build tag `opencv5`; en sistemas con OpenCV 5
solo (o ambas), compila y valida con:

```sh
make check-opencv5
```

Los targets `*-opencv5` pasan `-tags opencv5` y el bridge resuelve
`pkg-config opencv5`. Esa ruta no esta validada automaticamente en CI.

`cmd/sirah` accepts `-preview` to show the same OpenCV debug window while
the robot runs (needs a display; Q quits the vision loop). The camera can
only be opened by one process at a time, so close `cmd/vision` before
starting `cmd/sirah`.

## Manual camera test

El modelo forma parte del repositorio. Su version, fuente fijada y SHA256 estan
registrados en `models/face_detection_yunet_2023mar.onnx.sha256`. Verificalo sin
abrir la camara con:

```sh
make verify-model
```

Si es necesario restaurar el archivo desde upstream, la URL fijada es:

```sh
curl -L -o models/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/f12e12798e8314f7c074a6656816c048dcc95b7a/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
make verify-model
go run ./cmd/vision --debug

# Con OpenCV 5 instalado (opt-in):
go run -tags opencv5 ./cmd/vision --debug
```

The normal Go tests do not open a camera. The manual command uses camera index
0, V4L2, 640x480, and a requested capture rate of 15 FPS. Esta prueba manual de
camara no forma parte de `make check-opencv` ni es requisito para publicar el
codigo.

## Runtime integration

The main SIRAH process starts Vision as an independent camera worker when
explicitly enabled. Set `VISION_ENABLED=true` to activate it, or use the
`-preview` flag to activate it and open its HighGUI debug window. The
`-preview` flag takes precedence over `VISION_ENABLED=false`.
`VISION_MODEL` selects the model path and `VISION_CAMERA_INDEX` selects the
V4L2 index.

The worker publishes a mutex-protected latest `PerceptionSnapshot` for context
construction and a capacity-one latest-target channel for Motion. A short face
loss retains the smoothed target for 300 ms, but movement is not republished
while the current frame contains no face. After that tolerance the snapshot has
no target. Agent receives only the latest snapshot when a conversation turn
builds context; it never receives frames.
