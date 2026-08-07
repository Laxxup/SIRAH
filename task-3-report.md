# Task 3 Report: Typed Audio Diagnostics and Capture Validation

## Scope

Implemented only Task 3 from
`.superpowers/sdd/2026-08-06-headless-runtime-voice/task-3-brief.md`.
No Piper, Groq, SSE, Telegram, browser audio, or physical-control work was
added.

## Files

- Added `src/sirah/voice/diagnostics.py`: frozen `AudioMetrics`, terminal
  `AudioStage` values, strict runtime WAV/PCM validation, derived RMS/peak
  measurements, and capture-stage classification.
- Modified `src/sirah/voice/mic_capture.py`: validates captured S16_LE PCM,
  returns `(wav_data, metrics)`, verifies `arecord` survives startup, bounds
  stderr to 480 bytes, and wraps startup failures in a typed error. It holds no
  PCM as instance state and diagnostics hold metrics only.
- Modified `src/sirah/errors.py`: added `AudioCaptureError` and
  `AudioFormatError`, both subclasses of `SpeechInputError`.
- Added `tests/test_audio_diagnostics.py`: deterministic WAV, metrics,
  silence, low-signal, malformed PCM, and `arecord` startup tests.

## TDD Evidence

### RED 1

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: failed during collection with `ImportError`: `AudioCaptureError` and
`AudioFormatError` did not exist. This confirmed the diagnostic/error contract
was absent before implementation.

### GREEN 1

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `6 passed` after adding the diagnostics contract and capture lifecycle
implementation. A test-fixture scoping error was corrected before this run; it
did not alter production behavior.

### RED 2

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `test_capture_start_wraps_process_start_errors` failed with an untyped
`FileNotFoundError`, proving that `arecord` startup exceptions still escaped.

### GREEN 2

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `7 passed` after wrapping `Popen` `OSError` failures as
`AudioCaptureError`.

## Final Verification

All commands completed successfully:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy src tests --ignore-missing-imports
.venv/bin/python -m pytest -q
.venv/bin/python -m build
```

The build emitted only the pre-existing manifest warning for the excluded
`experiments` path and produced the sdist and wheel.

## Privacy and Authority

- `AudioMetrics` has no PCM field; it stores only counts, format, duration, RMS,
  peak, and silence state.
- No PCM, raw transcript, or prompt is logged or persisted by this task.
- `arecord` stderr is retained only for an immediate startup failure, capped at
  480 bytes; it never contains captured PCM.
- Capture device identity is not accepted by runtime client requests. Tasks 1-2
  already enforce the runtime-owned `DeviceRegistry` allowlist.

## Concern

Task 4 must construct `MicCapture` only from the runtime-selected
`DeviceRegistry` device and discard returned WAV bytes after the STT turn. Task
3 deliberately does not wire capture into the runtime or any client.

## Git

No commit was created. Existing uncommitted Task 1-2 changes were preserved.

## Review Fix Round 1

### RED

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `3 failed, 7 passed`.

- A WAV data chunk declaring four bytes while containing two was accepted.
- A child that exited after the first startup poll was accepted.
- A child that exited while recording produced the empty-audio path instead of
  `AudioCaptureError`.

### GREEN

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `10 passed`.

- `validate_wav()` now compares decoded bytes with the exact declared frame
  length and raises `AudioFormatError` for truncation.
- Startup performs two bounded process-liveness observations separated by one
  zero-delay event-loop yield.
- Capture checks child liveness before and after every read and before encoding
  a WAV, raising `AudioCaptureError` rather than classifying a child exit as
  silence.
- The fix adds no audio or transcript logging/persistence; stderr remains
  capped at 480 bytes for a typed process failure reason.

## Review Fix Round 2

### RED

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `2 failed, 10 passed`.

- A finite `arecord -d 1` process exiting with status zero at its configured
  duration was rejected as a capture failure.
- A zero-exit before that configured duration had no early-exit reason.

### GREEN

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `12 passed`.

- `MicCapture` records the effective integer `arecord -d` deadline at process
  creation.
- Only a zero exit at or after that deadline is accepted; its capture loop ends
  immediately and encodes its collected data.
- A zero exit before the deadline and every nonzero exit remain typed
  `AudioCaptureError` failures.
- An intermediate GREEN run exposed that the loop continued after an accepted
  finite completion; the loop now exits when the clean child completion clears
  the process. No audio/transcript logging or persistence was added.

## Review Fix Round 3

### RED

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `2 failed, 12 passed`.

- A zero-exit before the finite-capture deadline was accepted when `poll()` was
  delayed until after that deadline.
- Final PCM already buffered on an exited finite process was discarded before
  the terminal check, producing zero recorded bytes.

### GREEN

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `14 passed`.

- Terminal state samples the observation time before `poll()`, so a delayed
  return cannot turn an early zero-exit into expected completion.
- `read_chunk()` drains stdout before terminal processing; `record()` appends
  that final chunk before accepting clean finite completion.
- No PCM or transcript is logged or persisted; PCM remains only in the
  ephemeral return value for the active turn.

## Review Fix Round 4

### RED

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `1 failed, 14 passed`.

- A finite process with two queued `CHUNK_BYTES` PCM blocks retained only the
  first 4096-byte read before clean completion.

### GREEN

Command:

```bash
.venv/bin/python -m pytest tests/test_audio_diagnostics.py -q
```

Result: `15 passed`.

- Clean finite completion now drains stdout through EOF before clearing the
  process and appends every queued PCM block to the ephemeral capture result.
- Nonzero exits and finite exits before their configured deadline retain their
  existing typed `AudioCaptureError` behavior. No PCM or transcript is logged
  or persisted.
