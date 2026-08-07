# Persistent Piper Runtime Review

## Verdict

Request changes. The adapter removes Piper CLI discovery and passes the focused
offline tests, but runtime degradation is not exposed, playback cannot be
cancelled or bounded, and the operator/license documentation is inaccurate.

## Findings

1. `src/sirah/core/runtime.py:105-113`, `src/sirah/voice/tts_piper.py:103-105`: high. Runtime status is degraded only when initial model loading fails. A synthesis exception or an unsuccessful `AplayPlayer` completion sets `PiperTTS._failed`, but does not update the voice component from `READY` to `DEGRADED`; status clients therefore report healthy voice after a terminal Piper failure. Propagate post-start output health/failure to the registry and add a runtime-level assertion for synthesis and playback failures.

2. `src/sirah/voice/tts_piper.py:36-49`, `src/sirah/voice/tts_piper.py:122-124`: high. `AplayPlayer.play()` waits indefinitely for `aplay`, while `PiperTTS.stop()` only clears in-memory state and does not terminate or wait for the active player. A stalled playback retains the `AudioTurnCoordinator` lease indefinitely; runtime shutdown also cannot clean up that child process. Track the player process/task, use a bounded wait, and make `stop()` cancel/terminate it before releasing the lease. Cover cancellation, timeout, process cleanup, and lease release.

3. `docs/piper.md:24-30`: medium. The guide still says that Piper is a process receiving text over stdin and advertises `pw-play`; this implementation imports the Python API and invokes only `aplay`. Correct the instructions and supported-player statement so operators do not infer nonexistent CLI/stdin or PipeWire-player behavior.

4. `NOTICE:3-5`, `pyproject.toml:21-22`: medium. Installed allowed dependency `piper-tts 1.6.0` declares `GPL-3.0-or-later` (metadata home page: `OHF-voice/piper1-gpl`), but `NOTICE` gives no license identity and the task plan calls for an Apache-compatible third-party notice. `voice-piper`, `voice-full`, and `full` install that GPL dependency. State the actual license and obtain a licensing decision before representing the optional extra/full distribution as Apache-compatible.

## Verified

- `PiperTTS` loads its injected `PiperVoice` model once after `start()` and
  synthesizes through the Python API; no CLI discovery remains in the adapter.
- Service environment validates paired readable Piper model/config paths, and
  runtime composition owns the selected output device; clients cannot pass Piper
  configuration.
- Synthesis errors map to `TTS_FAILED`, unsuccessful playback maps to
  `PLAYBACK_FAILED`, and the human-turn `finally` releases its lease.
- Temporary WAV files are unlinked on the exercised synthesis and playback
  paths. The adapter does not retain the spoken text or WAV path after return.
- The physical smoke remains explicitly opt-in.

## Test Evidence

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_piper_runtime.py tests/test_runtime_service.py -q` | Passed: 19 tests |
| `.venv/bin/python -m pytest -q` | Passed; one physical smoke skipped |
| `.venv/bin/python -m ruff check src tests` | Passed |
| `.venv/bin/python -m mypy src tests --ignore-missing-imports` | Passed: 91 source files |
| `.venv/bin/python -m build` | Passed |
| `git diff --check` | Passed |

The existing focused tests use injected models and players, which is appropriate
for offline coverage, but do not exercise runtime status degradation, a hung or
cancelled `aplay`, runtime shutdown during playback, or the cleanup path for
the physical smoke.
