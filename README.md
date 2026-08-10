# SIRAH v0.3.0 — subsistema de ojos

SIRAH (**Sistema Inteligente Robótico de Asistencia Humana**) es el proyecto
general del robot. Este repositorio implementa el **subsistema de ojos** de
SIRAH v0.3.0: mirada 2D, parpadeo y tracking, con un runtime en PC/Raspberry
Pi, un ESP32 y seis servos (eye X, eye Y, cuatro párpados), guiados por una
webcam USB.

El nombre completo solo se usa en español y nunca se traduce.

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

Records live with this repository:

- `docs/adr/` — architecture decision record index (titles and status)
- `docs/components/` — wire protocol specification
- `docs/hardware/` — pin map and hardware evidence

Planning records that guided this repository are kept in the project's
internal workspace and are not part of this repository. Legacy code is
never copied into this repository (legacy is READ-ONLY).

## Hardware note

Servos ride on a PCA9685 driven over I2C (ADR-0011). `pins.h` holds the
channel map and `config/calibration.h` the corners — both VERIFIED
physically on 2026-08-09 (record in `docs/hardware/pin-map.md`).
Physical evidence wins over any future contradiction.

## License

Pending — decision of the project director. External designs and code
inspirations are credited, never presented as original work.