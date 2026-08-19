# Project Documentation P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SIRAH's repository operable, safe to evaluate, and ready to receive authentic laboratory media.

**Architecture:** Documentation separates operator actions, calibration authority, development checks, testing tiers, security/privacy and third-party notices. No photo, GIF or hardware verification claim is fabricated.

**Tech Stack:** Markdown, existing CLI, pytest, ruff, mypy.

## Global Constraints

- Refer to the project only as `SIRAH`; do not expand its name.
- Preserve `calibration.h` as physical authority and `actuators.yaml` as its tested mirror.
- Do not publish images of identifiable people without consent.

---

### Task 1: Operator and engineering guides

**Files:**
- Create: `docs/hardware/build.md`
- Create: `docs/calibration.md`
- Create: `docs/testing.md`
- Create: `docs/development.md`
- Modify: `README.md`

- [ ] **Step 1: Document hardware build**

Include the PCA9685 I2C address, six servo channels, external 5 V servo rail,
common ground, USB serial allowlist and the warning that the ESP32 USB supply is
not a servo power supply.

- [ ] **Step 2: Document calibration procedure**

Specify: disarm eyes, make one small change in `calibration.h`, run host tests,
mirror it in `actuators.yaml`, run `sirah-calibrate validate`, then record date,
hardware revision and observed mechanical limits in `pin-map.md`.

- [ ] **Step 3: Document testing and development commands**

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m mypy src
make -C firmware/sirah-eyes/tests/host core_tests
```

Explain unit, contract, integration, replay and HIL boundaries.

- [ ] **Step 4: Validate links and commands**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/python -m mypy src`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/hardware/build.md docs/calibration.md docs/testing.md docs/development.md
```

### Task 2: Security, privacy, notices and media preparation

**Files:**
- Create: `SECURITY.md`
- Create: `NOTICE`
- Create: `docs/privacy.md`
- Modify: `docs/assets/README.md`
- Modify: `CONTRIBUTING.md`

- [ ] **Step 1: Write security policy**

Direct reporters to GitHub private reporting after a repository remote exists;
until then, state that no public security-reporting channel is configured.
Document serial-device allowlisting and safe physical disarming before hardware
work.

- [ ] **Step 2: Write privacy and attribution notices**

State that camera captures require consent before publication, recordings stay
local by default, and third-party firmware attribution includes Adafruit PWM
Servo Driver under BSD-3-Clause.

- [ ] **Step 3: Prepare authentic media checklist**

Keep asset filenames and required captions: `hero-eyes-YYYY-MM-DD.jpg`,
`blink-sweep-YYYY-MM-DD.gif`, `wiring-YYYY-MM-DD.jpg`, and a terminal recording.
Do not add empty media files.

- [ ] **Step 4: Verify repository documentation links**

Run: `.venv/bin/python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SECURITY.md NOTICE docs/privacy.md docs/assets/README.md CONTRIBUTING.md
```
