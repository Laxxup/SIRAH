# SIRAH v0.3.0 — subsistema de ojos

SIRAH (**Sistema Inteligente Robótico de Asistencia Humana**) es el proyecto
general del robot. Este repositorio implementa el **subsistema de ojos** de
SIRAH v0.3.0: mirada 2D, parpadeo natural y tracking, con un runtime en
PC/Raspberry Pi, un ESP32 y seis servos (eye X, eye Y, cuatro párpados),
guiados por una webcam USB.

El nombre completo solo se usa en español y nunca se traduce.

## Qué es y qué NO es

**Es** el subsistema estable de ojos: runtime asyncio en PC (Raspberry
Pi 4/PC), protocolo de cable cerrado v1.0 PC↔ESP32, firmware ESP32 dueño
del parpadeo, easing y pose segura (ADR-0004), calibración verificada
físicamente y un gemelo conductual (FakeESP32) para probar **sin hardware**.

**NO es** (todavía): tracking de rostros con webcam (Stage 8, planificado),
inteligencia conversacional (laboratorio ADR-0007, OFF por defecto), ni
software de producción garantizado — es un prototipo de
investigación/educación con un núcleo estable y verificado.

## Status

| Componente | Estado |
|---|---|
| Protocolo v1.0 — gramática cerrada, 91 casos golden, doble parser Python/C++ gateado en CI | ✅ Normativo (Stage 3) |
| Firmware ESP32 — blink FSM, easing, watchdog, pose segura | ✅ VERIFIED 2026-08-09 |
| Runtime asyncio + registry (ready / degraded / off) | ✅ Stage 7 |
| Calibración (calibration.h ↔ actuators.yaml, test de consistencia) | ✅ VERIFIED 2026-08-09 |
| FakeESP32 (twin conductual) | ✅ 22 tests unitarios |
| Tracking 2D por webcam (percepción + gaze behavior) | ⏳ Stage 8 — pendiente |
| Laboratorio de inteligencia (ADR-0007) | OFF por diseño, scaffold |
| Tests | 169 passing |

## Quickstart — sin hardware (menos de 3 minutos)

```bash
pip install -e ".[cli,serial]"
sirah-runtime --fake --eyes
```

El runtime arma los ojos sobre el gemelo FakeESP32 y mantiene el
heartbeat hasta Ctrl-C. Los componentes fallidos **degradan**, no matan
la app.

Con hardware real (ESP32 + PCA9685 + 6 servos; wiring verificado en
[docs/hardware/pin-map.md](docs/hardware/pin-map.md), ADR-0011):

```bash
sirah-runtime --eyes
```

## Architecture

```
 PC / Raspberry Pi (runtime, src/sirah)          ESP32 (firmware/sirah-eyes)
┌──────────────────────────────────────┐        ┌─────────────────────────────┐
│ percepción (Stage 8)                 │        │ core: protocol · mapping ·  │
│  webcam → camera_source →            │        │       easing · blink_fsm    │
│         face_detector                │        │ platform: PCA9685 · pins.h  │
│        ↓                             │        │ config: calibration.h       │
│ behavior (Stage 8)                   │        │   (autoridad física)        │
│  gaze_behavior → SetpointGate →      │        └────────────┬────────────────┘
│        LostFacePolicy                │                     │ I2C + PWM
│        ↓                             │                     ▼
│ runtime: RuntimeApp (lifecycle +     │        6 servos — eye X/Y, 4 párpados
│ registry) + HeartbeatWriter          │
│        ↓                             │
│ EyeTransport (contrato, ADR-0002)    │
│  ├─ SerialTransport (serial real)    │──— serial v1.0: TARGET, BLINK,
│  └─ FakeESP32 (twin, ADR-0010) ──────┘     HEARTBEAT, STATUS, ERR
```

Regla de seguridad (ADR-0004): el PC **nunca** direcciona servos; solo
envía setpoints normalizados. Parpadeo, easing, límites y watchdog viven
en el firmware. El laboratorio de inteligencia (ADR-0007) está aislado y
OFF por defecto.

## Repository layout

```
src/sirah/     runtime Python asyncio: protocol · hardware · config ·
               runtime · cli (transport/ orphan, se decide en Stage 8)
firmware/      firmware ESP32 (core/ + platform/) + tests host C++
config/        runtime.toml (A9) + actuators.yaml (espejo de calibration.h)
tests/         unit · contract (91 golden) · integration · replay · hil
docs/          adr/ · components/protocol.md · hardware/ · architecture.md
               · quickstart.md · roadmap.md
laboratory/    laboratorio de inteligencia — OFF por defecto (ADR-0007)
```

## Testing

```bash
pytest tests -q                                   # 169 unit + contract
make -C firmware/sirah-eyes/tests/host core_tests      # host tests C++
make -C firmware/sirah-eyes/tests/host contract_checker  # gate doble parser
```

Estrategia de fake/replay/HIL en ADR-0010 ([docs/adr/](docs/adr/)).

## Documentation

- [docs/architecture.md](docs/architecture.md) — capas y fronteras
- [docs/quickstart.md](docs/quickstart.md) — guía paso a paso (fake primero)
- [docs/roadmap.md](docs/roadmap.md) — stages 1→16 con estado y criterios
- [docs/components/protocol.md](docs/components/protocol.md) — especificación normativa v1.0
- [docs/hardware/](docs/hardware/) — pin map, build y evidencia física
- [docs/adr/](docs/adr/) — índices de decisiones (11 ADRs)
- [CHANGELOG.md](CHANGELOG.md) — historial por stage
- [CONTRIBUTING.md](CONTRIBUTING.md) — cómo contribuir

## License

Apache-2.0 — ver [LICENSE](LICENSE). Código y diseños externos quedan
acreditados, nunca presentados como trabajo original: el driver de
servos del firmware usa la librería Adafruit PWM/Servo Driver
(BSD-3-Clause).