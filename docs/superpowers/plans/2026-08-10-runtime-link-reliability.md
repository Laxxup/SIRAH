# Runtime Link Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FakeESP32 advance at a stable tick rate under frequent polling and degrade the runtime exactly once after any outbound eye-link failure.

**Architecture:** FakeESP32 retains `_sim_ms` as its monotonic simulation time and tracks the next tick boundary separately. HeartbeatWriter reports its first transport exception through a callback owned by RuntimeApp, which shares its existing eye-degradation path with failed TARGET sends.

**Tech Stack:** Python 3.12, asyncio, pytest, pytest-asyncio.

## Global Constraints

- Keep `--fake --eyes` independent of optional perception dependencies.
- Preserve the physical-command boundary: only normalised commands reach EyeTransport.
- Count a link failure once and keep the runtime alive.

---

### Task 1: Tick accumulation in FakeESP32

**Files:**
- Modify: `src/sirah/hardware/fake_esp32.py`
- Test: `tests/unit/hardware/test_fake_esp32.py`

**Interfaces:**
- Produces: `FakeESP32._advance(ms: float) -> None` which calls `_step()` once per `tick_ms` boundary even when each `ms < tick_ms`.

- [ ] **Step 1: Write the failing test**

```python
def test_sub_tick_advances_accumulate_to_one_easing_step(fake):
    fake._target_x = 1.0
    fake.advance(10)
    fake.advance(10)
    assert fake._easer.x == pytest.approx(0.25)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/hardware/test_fake_esp32.py::test_sub_tick_advances_accumulate_to_one_easing_step -q`

Expected: FAIL because two 10 ms advances do not execute a 20 ms tick.

- [ ] **Step 3: Implement persistent tick boundaries**

```python
self._next_step_ms = float(tick_ms)

def _advance(self, ms: float) -> None:
    limit = self._sim_ms + ms
    while self._next_step_ms <= limit:
        self._step(self._next_step_ms)
        self._next_step_ms += self.tick_ms
    self._sim_ms = limit
```

- [ ] **Step 4: Run the fake transport tests**

Run: `.venv/bin/python -m pytest tests/unit/hardware/test_fake_esp32.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sirah/hardware/fake_esp32.py tests/unit/hardware/test_fake_esp32.py
```

### Task 2: Report heartbeat failures to RuntimeApp

**Files:**
- Modify: `src/sirah/runtime/heartbeat.py`
- Modify: `src/sirah/runtime/app.py`
- Test: `tests/unit/runtime/test_heartbeat.py`
- Test: `tests/integration/test_e2e_offline.py`

**Interfaces:**
- Consumes: `HeartbeatWriter(transport, cadence_s, on_failure)`.
- Produces: `RuntimeApp._degrade_eyes(exc: Exception) -> None`.

- [ ] **Step 1: Write the failing callback test**

```python
async def test_notifies_failure_once():
    errors: list[Exception] = []
    transport = RecordingTransport(); transport.fail = True
    await HeartbeatWriter(transport, 0.01, errors.append).run(asyncio.Event())
    assert len(errors) == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/runtime/test_heartbeat.py::test_notifies_failure_once -q`

Expected: FAIL because HeartbeatWriter has no failure callback.

- [ ] **Step 3: Add callback and unify degradation**

```python
except Exception as exc:
    if self._on_failure is not None:
        self._on_failure(exc)
    return

def _degrade_eyes(self, exc: Exception) -> None:
    if self._eyes_lost:
        return
    self.result.send_errors += 1
    self._eyes_lost = True
    self.registry.set("eyes", ComponentStatus.DEGRADED, str(exc))
```

- [ ] **Step 4: Verify E2E loss handling**

Run: `.venv/bin/python -m pytest tests/unit/runtime/test_heartbeat.py tests/integration/test_e2e_offline.py -q`

Expected: PASS; a stable TARGET no longer hides a broken heartbeat link.

- [ ] **Step 5: Commit**

```bash
git add src/sirah/runtime/heartbeat.py src/sirah/runtime/app.py tests/unit/runtime/test_heartbeat.py tests/integration/test_e2e_offline.py
```
