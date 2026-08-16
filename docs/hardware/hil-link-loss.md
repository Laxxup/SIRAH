# HIL Validation: Link Loss, Watchdog and Safe Pose

Physical validation procedure for the ESP32 eyes firmware watchdog
(protocol.md §10) and the runtime's degraded-eyes behavior. Requires
operator approval; not a CI gate (see `docs/testing.md`).

## Scope

- Firmware watchdog: after 3 s without a valid command line the firmware
  eases the gaze to the safe pose CENTER and holds it while the link stays
  down (§10.2/§10.3). Blinking continues.
- Firmware recovery: the first valid line after a timeout emits `READY 1`
  exactly once and the link returns to normal (§10.4).
- Runtime degradation: the eye-link supervisor reports the loss once and
  stops sending TARGETs; the app marks eyes DEGRADED and keeps running.

## Preconditions

- ESP32 flashed with the current `platform/main.ino`.
- Servos connected and powered from the external 5 V rail (see `build.md`).
- Host on `/dev/sirah-eyes` (or `/dev/ttyUSB*`), eyes armed via
  `sirah-runtime --eyes`.

## Procedure

1. **Baseline tracking.** Run the runtime with a face in view. Confirm the
   gaze follows and `STATE` replies converge to the commanded reference.
2. **Heartbeat alive.** Confirm the supervisor keeps sending `HEARTBEAT`
   every 1 s while the runtime is up (firmware stays tracking, watchdog
   never fires).
3. **Link loss.** Physically unplug the USB/serial cable (or the ESP32).
   - Confirm the gaze eases to CENTER and stays there while the cable is
     out (watchdog timeout ≤ 3 s).
   - Confirm blinking continues during the link-down window.
   - Confirm the host logs the eyes component as DEGRADED exactly once
     and stops sending TARGETs (no retry storm).
4. **Recovery.** Re-plug the cable.
   - Confirm the firmware emits `READY 1` exactly once.
   - Confirm tracking resumes as soon as the runtime sends a new
     `TARGET` (recentered reference; no restart required on either side).
5. **Recovery with the runtime already degraded.** With the runtime still
   up after step 3, verify the serial adapter reconnects or the operator
   restarts the runtime and the eyes re-arm cleanly.

## Acceptance

- The gaze never moves away from CENTER while the link is down.
- No unbounded retry loop: at most one DEGRADED transition and one
  `READY 1` per link-loss episode.
- Blinking is independent of the link in both directions.

## Offline twin

`tests/integration/test_e2e_offline.py::test_link_loss_safe_pose_recenters_firmware_via_watchdog`
exercises the same contract against FakeESP32: tracking → link break →
eyes DEGRADED → FakeESP32 watchdog eases to CENTER. Run it after any
change to the watchdog or the eye-link supervisor.