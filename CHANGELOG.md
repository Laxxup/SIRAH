# Changelog

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana** (only in
Spanish, never translated). Historico por stage del subsistema de ojos
(SIRAH v0.3.0). Formato: Conventional Commits.

## v0.3.0 — Milestone 1 (eyes core)

### Stage 7 (2026-08-09)
- `feat(runtime)`: runtime asyncio Python ≥ 3.12: `RuntimeApp` (lifecycle
  + registry ready/degraded/off), `HeartbeatWriter`, `SetpointGate`,
  `LostFacePolicy`, `sirah-runtime` CLI (`--fake --eyes`).
- `feat(config)`: loader TOML + env `SIRAH_*`, consistency
  `calibration.h` ↔ `actuators.yaml` (`sirah-calibrate validate`).
- 169 tests en verde; CI ampliado con job `unit`.

### Stage 6 (2026-08-09)
- `feat(hardware)`: FakeESP32 twin conductual (ADR-0009/0010): espeja
  mapping/easing/blink con reloj virtual inyectable. 22 tests.

### Stage 5 (2026-08-09)
- `feat(hardware)`: adapter serial USB-UART (`SerialTransport`,
  `EyeTransport` como contrato, ADR-0002). PTY loopback en scripts/.

### Stage 4 (2026-08-09)
- `feat(firmware)`: core de 6 actuadores (protocol, mapping, easing,
  blink_fsm) + platform (PCA9685, pins.h) + tests host C++.
- Calibración V6.12 VERIFIED físicamente (sweep manual, 2026-08-09);
  `calibration.h` como autoridad.

### Stage 3 (2026-08-08)
- `test`: corpus golden 91 casos + doble parser gateado en CI (Python
  `parse_line.py` ↔ C++ `contract_checker`).

### Stage 2 (2026-08-08)
- `docs`: especificación normativa del protocolo v1.0
  (docs/components/protocol.md, gramática cerrada, ADR-0003).

### Stage 1 (2026-08-08)
- `chore`: skeleton del monorepo, ADRs 0001–0010, LICENSE Apache-2.0.