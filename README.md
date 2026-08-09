# SIRAH v0.3.0

Humanoid eye subsystem: a PC/Raspberry Pi runtime, an ESP32 and six servos
(eye X, eye Y, four eyelids), guided by a USB webcam.

## Status

- **Milestone 1** (natural blinking + camera-driven 2D gaze): planning
  APPROVED by the director (2026-08-08).
- **Stage 1**: repository skeleton only. No production logic yet — no
  firmware, tracking, serial, blink or laboratory code exists in this
  repository at this stage.
- The PC↔ESP32 wire contract is a **placeholder until Stage 2**.

## Repository layout

```
docs/        ADR index, protocol spec placeholder, hardware docs
config/      (empty in Stage 1; actuator YAML + runtime TOML created in
             later stages)
src/sirah/   Python runtime package (skeleton)
firmware/    ESP32 firmware (skeleton; pins + calibration constants only)
tests/       test suites (placeholders; nothing to run yet)
laboratory/  Intelligence Laboratory scaffold — OFF by default (ADR-0007)
```

## Documentation

Planning truth lives in the READ-ONLY architecture-study workspace:

- ADRs 0001–0010: `sirah-architecture-study/reports/adr/`
- Architecture study: `sirah-architecture-study/reports/architecture-study-v0.3.0.md`
- Implementation plan (Milestone 1): `sirah-architecture-study/reports/implementation-plan-milestone-1.md`
- Initial calibration record: `sirah-architecture-study/reports/hardware/initial-calibration-2026-08-08.md`

This repository keeps its own indexes and hardware records; it never copies
legacy code (legacy is READ-ONLY).

## Hardware note

`firmware/sirah-eyes/platform/pins.h` holds the **working pin map (A5)**.
It is NOT definitive evidence: Stage 4 must verify every actuator
physically (sweep) and record the truth in `docs/hardware/pin-map.md`.
Physical evidence wins over this map.

## License

Pending — decision of the project director. External designs and code
inspirations are credited, never presented as original work.