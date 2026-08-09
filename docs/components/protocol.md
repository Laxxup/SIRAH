# Wire protocol (PC ↔ ESP32)

**Status: PLACEHOLDER.** The normative spec is written in Stage 2 of the
implementation plan. Nothing in this file is normative yet.

## Constraints already approved (must be honored by the Stage 2 spec)

- **A1 — Coordinates**: normalized x,y ∈ [-1,+1]; X: −1 left, 0 center,
  +1 right; Y: −1 down, 0 center, +1 up. Conversion to degrees and
  physical servo inversion live in calibration/config, never in behavior.
- **A2 — Heartbeat/watchdog**: HEARTBEAT 1 s; timeout 3 s; on link loss
  the ESP32 smoothly drives X/Y to center while autonomous blink
  continues; recovery without restart.
- **A3 — STATE semantics**: `STATE` reports the last COMMANDED position
  (servos have no position feedback); the limitation is documented
  explicitly in the Stage 2 spec.
- **A4 — Calibration**: NO calibration verb exists in the v0.3.0
  operational protocol; calibration is config-data, tools never open the
  serial port.

History: legacy SIRAH used several ad-hoc line-based protocols between
scripts and firmware; v0.3.0 replaces them with a single contract
(ADR-0003).