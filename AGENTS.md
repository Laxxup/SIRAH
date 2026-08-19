# SIRAH Agent Rules

SIRAH (Sistema Inteligente Robótico de Asistencia Humana) is an AI-powered
android/robotics platform.

It combines:

- conversational AI;
- speech recognition and synthesis;
- perception/computer vision;
- autonomous behavior policies;
- Python runtime orchestration;
- ESP32-based embedded control;
- actuators and expressive robotic eyes.

The project is currently in release stabilization.
## Project Structure

* `src/sirah/audio/` — audio capture, playback, VAD, STT and TTS providers
* `src/sirah/conversation/` — conversation lifecycle, coordination, context and LLM integration
* `src/sirah/runtime/` — application runtime, supervision, heartbeat and policies
* `src/sirah/hardware/` — hardware contracts, serial transport and FakeESP32
* `src/sirah/perception/` — camera, replay and YuNet perception
* `src/sirah/behavior/` — attention, gaze and behavior policies
* `src/sirah/config/` — configuration loading, validation and consistency
* `src/sirah/protocol/` — protocol parsing
* `firmware/sirah-eyes/` — ESP32 eye-control firmware
* `tests/unit/` — isolated unit tests
* `tests/contract/` — protocol and contract tests
* `tests/replay/` — deterministic replay tests
* `tests/integration/` — integration and offline E2E tests
* `tests/hil/` — hardware-in-the-loop support
* `laboratory/` — experimental work; keep isolated from stable runtime
* `docs/` — architecture, development, testing and release documentation

## Package Management

This project uses `uv`.

Use:

```bash
uv sync
uv run <command>
```

Do not install Python project dependencies with `pip` unless explicitly required for diagnosing an installation issue.

Do not commit virtual environments, caches or machine-specific files.

## Stabilization Workflow

For bug fixes:

1. Reproduce the problem.
2. Identify the root cause.
3. Add or identify regression coverage.
4. Confirm the test fails when appropriate.
5. Implement the smallest justified fix.
6. Run focused tests.
7. Run broader relevant test suites.
8. Inspect the final `git diff`.
9. Report remaining risks.

Do not mask failures merely to obtain a green test suite.

Never:

* delete or weaken a test simply because it fails;
* suppress exceptions without understanding their cause;
* loosen validation solely to accept broken behavior;
* perform unrelated cleanup during a bug fix;
* change public behavior without documenting the reason.

## Testing

Start with the narrowest relevant tests.

Examples:

```bash
uv run pytest tests/unit -q
uv run pytest tests/contract -q
uv run pytest tests/replay -q
uv run pytest tests/integration -q
```

For the complete Python test suite:

```bash
uv run pytest -q
```

Lint Python with:

```bash
uv run ruff check .
```

Only run additional type-checking or linting commands if they are actually configured in `pyproject.toml`.

### Test hierarchy

Prefer this progression when appropriate:

```text
unit
→ contract
→ replay
→ integration
→ HIL
```

Hardware-independent tests must remain runnable without physical hardware.

## Hardware and Firmware

Treat the Python↔ESP32 protocol as a compatibility boundary.

Do not change protocol semantics casually.

Before changing protocol behavior, inspect:

* `docs/components/protocol.md`
* `src/sirah/protocol/`
* `src/sirah/hardware/`
* `firmware/sirah-eyes/core/protocol.*`
* `tests/contract/`

Keep hardware-specific behavior behind the existing abstractions.

Preserve FakeESP32/offline testing unless explicitly changing the architecture.

Do not require physical hardware for ordinary unit, contract, replay or integration tests.

Firmware host tests live under:

```text
firmware/sirah-eyes/tests/host/
firmware/sirah-eyes/pca-calibrator/tests/host/
```

Inspect each Makefile before assuming available targets.

## Async and Runtime Safety

Be especially careful when modifying:

* cancellation;
* shutdown;
* background tasks;
* audio streams;
* reconnection;
* serial communication;
* heartbeat/supervisor behavior;
* shared mutable state.

Do not introduce fire-and-forget asyncio tasks without ownership and shutdown behavior.
Do not swallow `CancelledError` or cancellation-related behavior unintentionally.

Changes to runtime lifecycle code require regression coverage whenever practical.

## Conversation and Audio

Preserve clean boundaries between:

```text
capture
→ VAD
→ STT
→ conversation
→ LLM
→ TTS
→ playback
```

Avoid coupling providers directly when contracts already exist.

Provider-specific failures should not unnecessarily crash the entire runtime.

When changing latency-sensitive behavior, distinguish correctness fixes from performance optimizations.

## Experimental Code

`laboratory/` is experimental.

Experimental implementations must not silently become production dependencies.

Stable runtime code should not depend on laboratory code unless explicitly promoted through a reviewed architectural change.

## Documentation

Documentation must describe actual behavior.

Technical accuracy comes before stylistic rewriting.

For human-facing documentation:

1. verify behavior against implementation;
2. make the explanation clear;
3. improve readability without changing technical meaning.

Do not fabricate commands, configuration keys, features or supported hardware.

Important release documentation includes:

* `README.md`
* `docs/quickstart.md`
* `docs/testing.md`
* `docs/release.md`
* `CHANGELOG.md`

## Dependencies

Before adding a dependency:

1. determine whether the existing stack already solves the problem;
2. justify the dependency;
3. consider installation cost and Raspberry Pi compatibility where relevant;
4. update lock/configuration files correctly;
5. add tests for behavior relying on it.

Do not perform unrelated dependency upgrades during stabilization.

## Git

Use focused commits.

Preferred prefixes:

```text
fix:
test:
docs:
refactor:
chore:
```

Use `feat:` only when new functionality has explicitly been approved during stabilization.

Never merge automatically on behalf of the user.

Agents may prepare commits or diffs, but final integration remains a human decision.

## Agent Usage

Available specialist agents should be used intentionally.

Recommended:

* `@python-pro` — Python, asyncio and Python architecture
* `@cpp-pro` — firmware C/C++
* `@embedded-systems` — ESP32 and hardware integration
* `@test-writer` — regression and test design
* `@code-reviewer` — independent review
* `@performance-engineer` — only after correctness is established
* `@ai-engineer` — model/provider integration
* `@prompt-engineer` — conversation or model prompt behavior
* `@dependency-manager` — dependency audits
* `@docs-writer` / `@technical-writer` — documentation
* `@devops-engineer` — CI/release automation
* `@git-workflow-manager` — Git/release workflow

Avoid delegating to unrelated specialists merely because they are available.

## Skills

Load relevant skills on demand.

Currently useful skills include:

* `test-patterns`
* `dependency-audit`
* `git-release`
* `changelog-generate`
* `ci-pipeline`

Project-specific rules in this file override generic skill guidance when they conflict.

## Before Declaring a Task Complete

Confirm:

* the requested problem was actually addressed;
* relevant tests pass;
* no unrelated files were changed;
* the final diff was inspected;
* documentation remains accurate;
* no secrets or machine-specific paths were introduced;
* remaining risks are reported explicitly.

For release-critical changes, do not claim success solely because a single unit test passes.

## Robotics Safety

Treat commands that control physical hardware differently from pure software.

- Prefer bounded actuator values.
- Preserve calibration limits.
- Never remove hardware safety checks solely to make behavior appear correct.
- Avoid uncontrolled retry loops that can repeatedly actuate hardware.
- Hardware failures should degrade safely whenever practical.
- Verify protocol and calibration assumptions before changing motion behavior.
