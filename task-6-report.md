# Piper Review Fix Report

## Findings Addressed

- `PiperTTS` accepts a runtime-provided failure callback. The factory connects it
  to the existing voice component registry, so Piper load, synthesis, and
  playback failures mark voice `DEGRADED` after startup as well as during it.
- `AplayPlayer` now has a bounded wait. Timeout terminates the direct child;
  cancellation also terminates and waits for it before propagating cancellation.
  The existing `AudioTurnService` `finally` then releases the semiduplex lease.
- Piper documentation now describes only `PiperVoice.load`,
  `PiperVoice.synthesize_wav`, and `aplay -q -D`; stale CLI, stdin, `pw-play`,
  and absent voice-command claims were removed.
- `NOTICE` states that optional `piper-tts` is GPL-licensed and requires legal
  review before packaging, redistributing, or combining it with SIRAH or a voice.

## TDD Evidence

### RED

```text
.venv/bin/python -m pytest tests/test_piper_runtime.py tests/test_piper_runtime_status.py -q
..FFF..F
TypeError: PiperTTS.__init__() got an unexpected keyword argument 'on_failure'
TypeError: AplayPlayer.__init__() got an unexpected keyword argument 'timeout_s'
assert False  # cancelled aplay child was not terminated
KeyError: 'on_failure'
```

### GREEN

```text
.venv/bin/python -m pytest tests/test_piper_runtime.py tests/test_piper_runtime_status.py -q
........
```

The focused suite covers load failure status propagation, bounded playback
timeout, cancellation cleanup, playback degradation, WAV cleanup, and human
audio lease release.

## Physical Smoke

Not run: no operator opt-in or confirmed physical output was supplied. It
remains explicitly gated by `SIRAH_RUN_PIPER_PHYSICAL_SMOKE=1`.

No commit was created.
