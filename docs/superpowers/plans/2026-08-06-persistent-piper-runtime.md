# Persistent Piper Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide optional, persistent Piper Python API synthesis owned by `sirah-runtime`.

**Architecture:** The server environment selects readable external model/config files and an allowed output device. `PiperTTS` loads one model per runtime lifecycle and produces ephemeral WAV data; a separate runtime playback adapter renders that WAV to the server-selected output. Failures degrade voice turns without stopping the runtime.

**Tech Stack:** Python 3.14, asyncio, piper-tts optional dependency, pytest-asyncio.

## Global Constraints

- No Piper CLI discovery or client-selected audio configuration.
- Models, config, spoken text, and synthesized audio remain external or ephemeral.
- All audio uses the existing `AudioTurnCoordinator` lease.
- Unit tests are offline; physical smoke is explicit opt-in.

---

### Task 1: Persistent synthesizer and runtime playback

**Files:**
- Modify: `src/sirah/voice/tts_piper.py`
- Test: `tests/test_piper_runtime.py`

- [ ] Write failing tests for one model load, synthesis failure, playback failure, WAV cleanup, and lease release.
- [ ] Run the focused tests and confirm RED because the persistent lifecycle API is absent.
- [ ] Implement the injected Piper API loader, ephemeral WAV synthesis, and separate playback adapter.
- [ ] Run the focused tests and confirm GREEN.

### Task 2: Server-only Piper configuration and composition

**Files:**
- Modify: `src/sirah/runtime_service.py`
- Modify: `src/sirah/core/runtime.py`
- Modify: `src/sirah/factory.py`
- Test: `tests/test_runtime_service.py`

- [ ] Write failing configuration refusal and runtime propagation tests.
- [ ] Run focused tests and confirm RED.
- [ ] Validate model/config paths and compose Piper only in the runtime factory path.
- [ ] Run focused tests and confirm GREEN.

### Task 3: Packaging and operator documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/piper.md`
- Modify: `docs/architecture/ADR-005-piper-cli-runtime.md`
- Modify: `deploy/systemd/runtime.env.example`
- Modify: `CHANGELOG.md`
- Create: `NOTICE`
- Create: `tests/test_piper_physical_smoke.py`

- [ ] Add the optional dependency, Apache-compatible third-party notice, server configuration reference, and opt-in smoke.
- [ ] Run project verification and record RED/GREEN evidence in `task-5-report.md`.
