# Headless Runtime Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SIRAH a headless runtime with one authority for physical I/O and a demonstrably working, observable server-audio turn.

**Architecture:** `SirahRuntime` owns the single `build_system()` assembly, device registry, audio leases, camera, Cortex-facing orchestration, and hardware gateway. Web Lab and CLI become authenticated `RuntimeClient` adapters with explicit capabilities; no client imports or invokes hardware adapters. The Piper Python API runs in a supervised persistent worker and returns synthesized PCM/WAV only; runtime remains the sole ALSA playback owner.

**Tech Stack:** Python 3.14, asyncio, systemd, ALSA/PipeWire, `piper-tts` optional dependency, faster-whisper and Flask client UI.

## Global Constraints

- Work only in `/home/laxxup/SIRAHv0.2`.
- Python 3.14 is the target; lower it only if a concrete dependency proves incompatible.
- `build_system(profile=...)` remains the only Cortex-facing factory and is callable only by `SirahRuntime`.
- `SirahRuntime` is the sole authority for ALSA, camera, Piper, Cortex, WorldState, ESP32 and future hardware.
- Hardware starts disarmed; no client protocol accepts PWM, angles, serial paths or shell input.
- Every human or autonomous operation has a `turn_id`; local human input preempts autonomy.
- Errors extend `SirahError` and diagnostics never persist PCM, raw transcripts, prompts or conversations.
- Transcripts may be returned only in the ephemeral result of their own turn; never log or persist them.
- `DeviceRegistry` owns the capture/output inventory and allowlist; client requests never contain ALSA names.
- `RuntimeClient` uses a Unix domain socket transport; Web Lab and CLI never import or instantiate `SirahRuntime`.
- Do not add SSE, Telegram, eyes, PCA9685 control, browser microphone capture, Groq STT or physical control in this phase.
- Tests remain deterministic and hardware-free; physical smokes are explicit opt-in commands.

## File Structure

- Create: `src/sirah/core/runtime.py` - lifecycle supervisor and sole hardware authority.
- Create: `src/sirah/core/runtime_client.py` - generic client protocol, client identity and capability ACL.
- Create: `src/sirah/core/runtime_transport.py` - Unix domain socket server/client transport.
- Create: `src/sirah/core/devices.py` - configured capture/output inventory and allowlist.
- Create: `src/sirah/voice/diagnostics.py` - immutable per-turn audio metrics and terminal stage/outcome.
- Create: `src/sirah/voice/audio_service.py` - one leased voice pipeline from capture through playback.
- Create: `src/sirah/voice/piper_worker.py` - supervised persistent Python-API Piper inference worker; no ALSA access.
- Modify: `src/sirah/voice/mic_capture.py` - validated ALSA process lifecycle and PCM metrics source.
- Modify: `src/sirah/voice/stt_whisper.py` - persistent lifecycle, typed results and bounded diagnostics.
- Modify: `src/sirah/voice/tts_piper.py` - replace ambiguous executable probing with worker client contract.
- Modify: `src/sirah/factory.py`, `src/sirah/errors.py`, `src/sirah/types.py` - runtime composition and typed contracts.
- Modify: `src/sirah/web_server.py`, `src/sirah/console.py` - become Unix-socket RuntimeClient adapters only.
- Create: `tests/test_runtime_client.py`, `tests/test_audio_diagnostics.py`, `tests/test_audio_service.py`, `tests/test_piper_worker.py`.
- Modify: `tests/test_web_server.py`, `tests/test_console.py`, `tests/test_voice.py`, `tests/test_audio_turn.py`, `docs/piper.md`, `README.md`, `CHANGELOG.md`, `scripts/deploy_pi.sh`.

### Task 1: Runtime Client ACL Contract

**Files:**
- Create: `src/sirah/core/runtime_client.py`
- Modify: `src/sirah/errors.py`, `src/sirah/types.py`
- Test: `tests/test_runtime_client.py`

**Interfaces:**
- Produces `ClientKind`, `ClientCapabilities`, `RuntimeClient`, `RuntimeRequest`, and `RuntimeAccessDeniedError`.
- Client capabilities are only `conversation.submit`, `status.read`, `diagnostics.read`, and `laboratory.manual_text` initially; no request carries a device identifier.

- [ ] Write failing tests proving Web Lab and CLI can submit text/read status, while requests containing `device`, `serial`, `pwm`, `angle`, `shell`, or `arm` are rejected.
- [ ] Run `pytest tests/test_runtime_client.py -q`; expect missing contracts.
- [ ] Implement immutable request metadata, ACL lookup by client kind, and rejection before any runtime call.
- [ ] Run `pytest tests/test_runtime_client.py -q`; expect pass.

### Task 2: Headless Runtime Ownership

**Files:**
- Create: `src/sirah/core/runtime.py`, `src/sirah/core/runtime_transport.py`, `src/sirah/core/devices.py`
- Modify: `src/sirah/factory.py`, `src/sirah/core/orchestrator.py`, `src/sirah/__init__.py`, `pyproject.toml`
- Test: `tests/test_runtime_client.py`, `tests/test_factory.py`

**Interfaces:**
- Consumes `RuntimeClient` requests.
- Produces `SirahRuntime.start()`, `stop()`, `submit_text()`, `submit_local_voice_turn()`, read-only `snapshot()`, and a `RuntimeTransport` Unix socket endpoint.

- [ ] Write failing tests for one runtime assembly, disarmed hardware state, Unix-socket client disconnection not stopping runtime, and DeviceRegistry rejection of an unknown capture/output device.
- [ ] Run focused tests; expect missing runtime.
- [ ] Implement a runtime supervisor that alone invokes `build_system()`, owns DeviceRegistry and serves RuntimeClient requests through a Unix domain socket.
- [ ] Run focused tests; expect pass.

### Task 3: Typed Audio Diagnostics and Capture Validation

**Files:**
- Create: `src/sirah/voice/diagnostics.py`
- Modify: `src/sirah/voice/mic_capture.py`, `src/sirah/errors.py`
- Test: `tests/test_audio_diagnostics.py`

**Interfaces:**
- Produces `AudioMetrics(bytes_count, duration_ms, sample_rate, channels, sample_width, rms, peak, is_silent)` and terminal stages `capture_failed`, `silence`, `signal_low`, `stt_empty`, `intelligence_failed`, `tts_failed`, `playback_failed`, `completed`.

- [ ] Write deterministic PCM tests for WAV validation, RMS/peak, silence, low-level audio, odd byte count and exited `arecord` with bounded stderr reason.
- [ ] Run `pytest tests/test_audio_diagnostics.py -q`; expect failure.
- [ ] Make `MicCapture.start()` verify the child stays alive, retain bounded stderr, validate PCM format, and return metrics without retaining audio.
- [ ] Run focused tests; expect pass.

### Task 4: Single Leased Voice Pipeline

**Files:**
- Create: `src/sirah/voice/audio_service.py`
- Modify: `src/sirah/voice/coordinator.py`, `src/sirah/types.py`
- Test: `tests/test_audio_service.py`, `tests/test_audio_turn.py`

**Interfaces:**
- Consumes one configured capture device and `AudioTurnCoordinator`.
- Produces `VoiceTurnResult(turn_id, stage, diagnostics, transcript, response, tts_completion)` and never raises an untyped terminal error to a client.

- [ ] Write failing tests for generated `turn_id`, human-input priority, concurrent-turn rejection, stage-specific outcomes and release after every terminal branch.
- [ ] Run focused tests; expect failure.
- [ ] Implement `AudioTurnService` as the only local microphone and speaker caller; pause autonomy while an input or output lease exists.
- [ ] Run focused tests; expect pass.

### Task 5: Persistent STT With Controlled Fallback

**Files:**
- Modify: `src/sirah/voice/stt_whisper.py`, `src/sirah/voice/audio_service.py`, `src/sirah/factory.py`
- Test: `tests/test_audio_service.py`, `tests/test_voice.py`

**Interfaces:**
- `SpeechRecognizer` exposes `start()`, `transcribe(wav, turn_id)`, `health()`, and `stop()`.
- Initial production recognizer is persistent Whisper. Groq is explicitly out of scope for this phase.

- [ ] Write failing tests that prove one Whisper model load across two turns and preserve typed `stt_empty` versus `stt_failed`.
- [ ] Run focused tests; expect failure.
- [ ] Keep Whisper loaded for runtime lifetime and add bounded STT latency/transcript diagnostics without logging text.
- [ ] Run focused tests; expect pass.

### Task 6: Persistent Piper Python Worker and Runtime Playback

**Files:**
- Create: `src/sirah/voice/piper_worker.py`
- Modify: `src/sirah/voice/tts_piper.py`, `src/sirah/voice/audio_service.py`, `pyproject.toml`
- Test: `tests/test_piper_worker.py`, `tests/test_audio_service.py`

**Interfaces:**
- Worker loads `PiperVoice` once using `piper-tts`; it synthesizes audio only.
- Runtime playback adapter owns `pw-play` or configured ALSA/PipeWire output and reports a separate completion.

- [ ] Write failing fake-worker tests for one model load, worker timeout/restart, synthesis failure and playback failure without runtime termination.
- [ ] Run focused tests; expect failure.
- [ ] Implement a supervised one-request Piper worker using the Python API, bounded IPC and no device access; remove `/usr/bin/piper` discovery.
- [ ] Add `piper-tts` as an optional, version-pinned runtime extra and document GPL-3.0-or-later deployment implications.
- [ ] Run focused tests; expect pass.

### Task 7: Convert Existing Clients to Runtime Adapters

**Files:**
- Modify: `src/sirah/web_server.py`, `src/sirah/console.py`, `tests/test_web_server.py`, `tests/test_console.py`

**Interfaces:**
- Web Lab and CLI use `RuntimeClient`; neither imports `MicCapture`, `WhisperSTT`, `PiperTTS`, serial bridge, camera loop, or `build_system()` directly.

- [ ] Write failing tests ensuring `/api/listen` returns `turn_id`, terminal stage and sanitized diagnostics; verify client disconnect cannot cancel runtime work.
- [ ] Run focused tests; expect failure.
- [ ] Replace direct hardware construction with runtime requests and expose only read-only status/diagnostics to Web Lab and CLI.
- [ ] Bind Web Lab locally by default; preserve Flask only as an optional client service.
- [ ] Run focused tests; expect pass.

### Task 8: Hardware Evidence and Operational Packaging

**Files:**
- Modify: `scripts/deploy_pi.sh`, `docs/piper.md`, `README.md`, `CHANGELOG.md`
- Create: `scripts/smoke_server_voice.py`

**Interfaces:**
- Opt-in smoke returns one sanitized report per stage and exits nonzero for any non-`completed` terminal stage.

- [ ] Write a fake-device smoke test verifying the report has device identity, metrics, STT provider, stage latencies and no audio/text payload.
- [ ] Run its unit test; expect failure.
- [ ] Implement an explicit hardware smoke requiring `SIRAH_RUN_SERVER_VOICE_SMOKE=1`, configured capture/output devices and an operator voice prompt.
- [ ] Run the full quality gate plus the opt-in smoke on target hardware. Accept only when one local turn reaches `completed` and each forced failure maps to the correct typed stage.
- [ ] Update documentation with exact hardware evidence and no claims beyond the measured platform.

## Completion Gate

The runtime phase is complete only when an operator can run an opt-in smoke on the target machine and receive one `turn_id` with: device identity, valid WAV format, duration/RMS/peak/bytes, persistent STT result, IA latency, Piper synthesis latency, playback completion, and no persisted audio or transcript.
