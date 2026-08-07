# Task 4 Report

## Scope

Implemented only Task 4: a leased local voice pipeline, its terminal result
contract, coordinator lease transfer, and focused tests. Tasks 1-3 were left
intact. No Piper, Groq, Telegram, SSE, physical control, UI, transcript logging,
or transcript persistence was added.

## TDD Evidence

RED command:

```text
.venv/bin/python -m pytest tests/test_audio_service.py tests/test_audio_turn.py -q

ERROR tests/test_audio_service.py
ModuleNotFoundError: No module named 'sirah.voice.audio_service'
```

GREEN command:

```text
.venv/bin/python -m pytest tests/test_audio_service.py tests/test_audio_turn.py -q
...............                                                          [100%]
```

The focused suite covers generated turn IDs, terminal stages, lease release on
every branch, concurrent human-turn rejection, and autonomous output rejection
while a human input lease is held.

## Final Verification

```text
.venv/bin/python -m ruff check src tests
All checks passed!

.venv/bin/python -m mypy src tests --ignore-missing-imports
Success: no issues found in 87 source files

.venv/bin/python -m pytest -q
........................................................................ [ 30%]
........................................................................ [ 60%]
........................................................................ [ 90%]
......................                                                   [100%]

git diff --check
(no output; exit status 0)
```

## P0 Integration Follow-up

`SirahRuntime` now resolves its configured capture identifier through
`DeviceRegistry`, constructs `MicCapture` through its internal factory, and
installs the resulting `AudioTurnService`. Local voice turns call that service.
The service alone invokes speech input/output ports. `SirahOrchestrator`,
`SituationalCoordinator`, `AutonomousCoordinator`, and `VisionLoop` route
autonomous output through the service. Human input waits for autonomous output;
autonomy waits while a human lease is held. A failed input-to-output transfer
does not invoke TTS. Capture metrics are returned unchanged in the result.

### P0 TDD Evidence

RED command:

```text
.venv/bin/python -m pytest tests/test_audio_service.py tests/test_audio_turn.py tests/test_factory.py -q
........FF.......F
FAILED tests/test_audio_service.py::test_human_turn_preserves_mic_capture_metrics_in_its_terminal_result
TypeError: AudioTurnService.__init__() got an unexpected keyword argument 'capture'
FAILED tests/test_audio_service.py::test_human_turn_waits_for_autonomous_output_instead_of_capture_failure
AssertionError: assert not True
FAILED tests/test_factory.py::test_runtime_installs_and_calls_its_audio_service
TypeError: SirahRuntime.__init__() got an unexpected keyword argument 'capture_device'
```

GREEN command:

```text
.venv/bin/python -m pytest tests/test_audio_service.py tests/test_audio_turn.py tests/test_factory.py tests/test_orchestrator.py tests/test_situational.py tests/test_autonomous.py -q
.................................                                        [100%]
```

## P0 Alias-Value Normalization Follow-up

Nested string values are normalized with `strip().lower()` before prohibited
hardware alias matching. This rejects whitespace-padded `hw` and `card` values
without changing device authority or capture-byte flow.

### Alias-Value TDD Evidence

RED command:

```text
.venv/bin/python -m pytest tests/test_runtime_client.py -q
.............FF.................
FAILED test_nested_whitespace_padded_hardware_alias_value_is_rejected[ hw ]
FAILED test_nested_whitespace_padded_hardware_alias_value_is_rejected[ card ]
```

GREEN command:

```text
.venv/bin/python -m pytest tests/test_runtime_client.py -q
................................                                         [100%]
```

### Bypass Audit

`MicCapture` retains the only `arecord` invocation and is constructed by the
runtime solely for `AudioTurnService`. Direct `speak()` calls occur only in
`AudioTurnService`. The Pi bridge TTS playback bypass was disabled. `PiperTTS`
retains its existing `aplay` implementation as the legacy optional output
adapter; changing it is explicitly excluded by this Task 4 P0 request and is
deferred to Task 6. `PiperTTS` is instantiated only as the factory-selected
output adapter and is invoked through `AudioTurnService`.

## P0 Capture-to-Recognition Follow-up

The runtime path is `DeviceRegistry` configured capture device -> runtime
constructed `MicCapture` -> immutable `CapturedAudio` -> recognizer
`transcribe(CapturedAudio.data)` -> intelligence -> TTS. `CapturedAudio` carries the
original WAV bytes, format fields, duration, and the exact `AudioMetrics`
instance returned to `VoiceTurnResult`. `AudioTurnService` has no
`SpeechInputPort.listen()` call and performs one capture record per human turn.

`DeviceRegistry` owns the configured capture selection. `SirahRuntime` accepts
the registry, not a capture-device override or generated allowlist. Clients
can request only the abstract `local_voice_turn.submit` capability; device
metadata and aliases are rejected before runtime dispatch.

### Capture TDD Evidence

RED command:

```text
.venv/bin/python -m pytest tests/test_audio_service.py tests/test_factory.py tests/test_runtime_client.py -q
ERROR tests/test_audio_service.py
ImportError: cannot import name 'CapturedAudio' from 'sirah.voice.diagnostics'
ERROR tests/test_factory.py
ImportError: cannot import name 'CapturedAudio' from 'sirah.voice.diagnostics'
```

GREEN command:

```text
.venv/bin/python -m pytest tests/test_audio_service.py tests/test_factory.py tests/test_runtime_client.py -q
.........................................                                [100%]
```

### Capture Audit

```text
Search: MicCapture\(|arecord|\.listen\(
Result: only src/sirah/voice/mic_capture.py contains arecord.
```

`MicCapture` is the authorized capture adapter and is constructed only by
`SirahRuntime` for `AudioTurnService`. No production `listen()` caller remains.

## P0 Review Follow-up

`SirahRuntime` now supplies a capture factory to `AudioTurnService`, which
constructs its `MicCapture` inside each local human turn. Each turn records
exactly once. The `hw` and `card` aliases are prohibited alongside the existing
device aliases, with whitespace-normalized nested metadata keys rejected before
runtime dispatch.

### Review TDD Evidence

RED command:

```text
.venv/bin/python -m pytest tests/test_factory.py tests/test_runtime_client.py -q
..F.....FF.....F.................
FAILED test_runtime_constructs_one_capture_per_local_voice_turn: expected 2 captures, got 1
FAILED test_prohibited_request_fields_are_rejected_before_runtime_dispatch[hw]
FAILED test_prohibited_request_fields_are_rejected_before_runtime_dispatch[card]
FAILED test_normalized_nested_hardware_alias_is_rejected_before_runtime_dispatch
```

GREEN command:

```text
.venv/bin/python -m pytest tests/test_factory.py tests/test_runtime_client.py -q
.................................                                        [100%]
```

## Web Lab Repair Round 1

### Scope

Web Lab remains an HTTP `RuntimeClient` adapter. No runtime-owned microphone,
camera, TTS, Piper, autonomy, SSE, Telegram, or hardware support was added.

### RED

```text
.venv/bin/python -m pytest -q tests/test_web_server.py
.FF.....F.....FFF.F
```

The failures showed that `uninitialised` and `degraded` components were marked
healthy, a non-string chat value reached Flask as an HTML 500, malformed runtime
results were accepted or escaped as HTML 500, and the template had no explicit
unavailable-status or structured chat-error rendering path.

### GREEN

```text
.venv/bin/python -m pytest -q tests/test_web_server.py
...................                                                      [100%]
```

- Health is true only when every reported component is `ready`; degraded,
  uninitialised, error, and shutdown voice states are explicitly unavailable.
- Status and chat failures set the browser indicator to error and label voice as
  unavailable. Chat and voice controls render the fixed JSON `error.message`.
- Invalid JSON, non-object/non-string chat requests, and malformed results from
  chat, status, or local voice calls return fixed safe JSON errors. Runtime
  result details are not exposed.

## Web Lab Repair Round 2

### Scope

This round changes only Web Lab response validation and its focused tests. The
runtime remains the sole owner of audio and hardware resources.

### RED

```text
.venv/bin/python -m pytest -q tests/test_web_server.py
......F.....FFFFFFFFFFFFF........
```

The empty component snapshot was reported healthy. Thirteen malformed nested
voice-result fields, including metrics, transcript/response, and TTS
completion fields, were incorrectly emitted as successful listen responses.

### GREEN

```text
.venv/bin/python -m pytest -q tests/test_web_server.py
.................................                                        [100%]
```

- Empty component snapshots are unhealthy and report voice unavailable.
- `/api/listen` validates every exposed diagnostics field, including integer
  types, positive format values, non-negative counts/levels, RMS/peak bounds,
  and the boolean silence flag.
- Optional transcript/response values must be strings when present. TTS
  completion must have a non-empty operation ID, boolean success flag, and
  non-negative numeric duration.
- Any malformed nested result returns the existing fixed `502`
  `invalid_runtime_result` JSON envelope without exposing runtime data.

## Web Lab Repair Round 3

### RED

```text
.venv/bin/python -m pytest -q tests/test_web_server.py
.........................F........
```

`tts_completion.duration_ms=float('inf')` was accepted and emitted as an HTTP
200 response.

### GREEN

```text
.venv/bin/python -m pytest -q tests/test_web_server.py
..................................                                       [100%]
```

TTS completion durations now require finite, non-negative numeric values.
Infinity and NaN therefore use the existing safe `502 invalid_runtime_result`
response rather than being serialized into a successful API result.

### NaN Regression

Added `tts_completion.duration_ms=float('nan')` to the existing non-finite
duration parameterization without changing production code.

```text
.venv/bin/python -m pytest -q tests/test_web_server.py
...................................                                      [100%]
```
