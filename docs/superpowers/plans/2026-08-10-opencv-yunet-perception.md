# OpenCV YuNet Perception Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional USB-camera and local YuNet detector path that produces existing `GazeTarget` values without changing eye safety boundaries.

**Architecture:** OpenCV remains behind optional module imports. A camera source supplies opaque frames, a detector converts the largest valid face to A1 coordinates, and a model installer explicitly verifies and stores the ONNX artifact before detector construction.

**Tech Stack:** Python 3.12, asyncio, OpenCV optional extra, NumPy, SHA-256, pytest.

## Global Constraints

- Do not add OpenCV, NumPy, a camera, or a model requirement to base install or CI.
- Never download a model at import time or runtime startup.
- The detector returns `GazeTarget | None`; smoothing and eye commands remain outside it.

---

### Task 1: Model manifest and explicit installer

**Files:**
- Create: `src/sirah/perception/models.py`
- Create: `src/sirah/cli/models.py`
- Modify: `pyproject.toml`
- Test: `tests/unit/perception/test_models.py`

**Interfaces:**
- Produces: `YuNetModel(url: str, sha256: str, filename: str)` and `install_yunet(destination: Path) -> Path`.
- Produces CLI: `sirah-models yunet --destination PATH`.

- [ ] **Step 1: Write failing checksum tests**

```python
def test_installer_rejects_checksum_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "urlopen", lambda _: io.BytesIO(b"wrong"))
    with pytest.raises(ValueError, match="SHA-256"):
        models.install_yunet(tmp_path)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/perception/test_models.py -q`

Expected: FAIL because the installer does not exist.

- [ ] **Step 3: Implement verified download**

```python
payload = urlopen(YUNET.url, timeout=30).read()
if hashlib.sha256(payload).hexdigest() != YUNET.sha256:
    raise ValueError("YuNet model SHA-256 mismatch")
destination.mkdir(parents=True, exist_ok=True)
path = destination / YUNET.filename
path.write_bytes(payload)
return path
```

- [ ] **Step 4: Add the console script and ignore model artifacts**

```toml
[project.scripts]
sirah-models = "sirah.cli.models:main"
```

Add `models/` to `.gitignore`.

- [ ] **Step 5: Verify tests**

Run: `.venv/bin/python -m pytest tests/unit/perception/test_models.py -q`

Expected: PASS without network access.

- [ ] **Step 6: Commit**

```bash
git add src/sirah/perception/models.py src/sirah/cli/models.py pyproject.toml .gitignore tests/unit/perception/test_models.py
```

### Task 2: Camera source and YuNet detector

**Files:**
- Create: `src/sirah/perception/opencv_camera.py`
- Create: `src/sirah/perception/yunet.py`
- Test: `tests/unit/perception/test_yunet.py`

**Interfaces:**
- Produces: `OpenCVCameraSource(device: int | str, width: int, height: int)` implementing `CameraSource`.
- Produces: `YuNetFaceDetector(model_path: Path, score_threshold: float = 0.8)` implementing `FaceDetector`.

- [ ] **Step 1: Write pure mapping tests**

```python
def test_bbox_center_maps_to_a1_coordinates():
    assert map_bbox_to_target((0, 0, 20, 20), 100, 100).x == pytest.approx(-0.8)
    assert map_bbox_to_target((0, 0, 20, 20), 100, 100).y == pytest.approx(0.8)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/perception/test_yunet.py -q`

Expected: FAIL because mapping and detector helpers do not exist.

- [ ] **Step 3: Implement pure selection and mapping**

```python
def select_largest_face(rows: Iterable[FaceRow]) -> FaceRow | None:
    return max(rows, key=lambda row: row.width * row.height, default=None)

def map_bbox_to_target(bbox: BBox, width: int, height: int) -> GazeTarget:
    x = max(-1.0, min(1.0, 2 * (bbox.center_x / width) - 1))
    y = max(-1.0, min(1.0, 1 - 2 * (bbox.center_y / height)))
    return GazeTarget(x, y, confidence=bbox.score)
```

- [ ] **Step 4: Implement optional OpenCV adapters**

Import `cv2` only in adapter constructors. Raise `RuntimeError` with
`pip install -e ".[perception]"` when unavailable, and raise `FileNotFoundError`
when `model_path` is absent.

- [ ] **Step 5: Verify pure tests and type checking**

Run: `.venv/bin/python -m pytest tests/unit/perception -q && .venv/bin/python -m mypy src/sirah/perception`

Expected: PASS without the optional extra.

- [ ] **Step 6: Commit**

```bash
git add src/sirah/perception/opencv_camera.py src/sirah/perception/yunet.py tests/unit/perception/test_yunet.py
```

### Task 3: Explicit runtime wiring and replay

**Files:**
- Create: `src/sirah/perception/replay.py`
- Modify: `src/sirah/cli/run.py`
- Modify: `config/runtime.toml`
- Test: `tests/unit/perception/test_replay.py`
- Test: `tests/integration/test_e2e_offline.py`

**Interfaces:**
- Produces: `ReplayCameraSource(frames: Iterable[object])` implementing `CameraSource`.
- Produces CLI flags: `--camera-device`, `--yunet-model`, and `--replay`.

- [ ] **Step 1: Write replay EOF test**

```python
async def test_replay_returns_frames_then_none():
    source = ReplayCameraSource(["a", "b"])
    await source.start()
    assert (await source.next_frame()).payload == "a"
    assert (await source.next_frame()).payload == "b"
    assert await source.next_frame() is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/perception/test_replay.py -q`

Expected: FAIL because ReplayCameraSource does not exist.

- [ ] **Step 3: Implement replay and explicit CLI construction**

The CLI constructs camera/detector only when both `--camera-device` and
`--yunet-model` are supplied. It rejects one without the other using
`parser.error`. `--replay` is mutually exclusive with `--camera-device`.

- [ ] **Step 4: Run E2E and replay tests**

Run: `.venv/bin/python -m pytest tests/unit/perception/test_replay.py tests/integration/test_e2e_offline.py -q`

Expected: PASS; existing fake E2E remains free of OpenCV.

- [ ] **Step 5: Commit**

```bash
git add src/sirah/perception/replay.py src/sirah/cli/run.py config/runtime.toml tests/unit/perception/test_replay.py tests/integration/test_e2e_offline.py
```
