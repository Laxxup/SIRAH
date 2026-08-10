# SIRAH v0.3.0 — Roadmap

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana** (only in
Spanish, never translated). Stages of the eyes subsystem, with status and
exit criteria. Mostrar el estado real: lo que está hecho, lo que entra en
v0.3.0 y lo que no.

## Hecho (Milestone 1 — v0.3.0)

| Stage | Título | Estado | Evidencia |
|---|---|---|---|
| 1 | Skeleton del monorepo | ✅ | ADR-0008 |
| 2 | Especificación normativa del protocolo v1.0 | ✅ | docs/components/protocol.md |
| 3 | Parsers Python + C++ + corpus golden (91 casos) | ✅ gate en CI | doble parser, test_parsers_contract |
| 4 | Firmware 6 actuadores: core, platform, host tests + calibración V6.12 | ✅ VERIFIED 2026-08-09 | firmware/sirah-eyes, calibration.h |
| 5 | Adapter serial (EyeTransport) | ✅ | serial_adapter.py, tests 45 |
| 6 | FakeESP32 twin conductual | ✅ 22 tests | ADR-0009/0010 |
| 7 | Runtime asyncio + registry + policies + CLI | ✅ 169 tests | app.py, cli/run.py |

## Planeado

| Stage | Título | Estado | Criterios de salida |
|---|---|---|---|
| 8 | Tracking 2D: percepción (camera_source, face_detector) + gaze_behavior | ✅ | Protocolos nominales, pipeline cableado, OpenCV/YuNet opcional, E2E offline y `lost_face_center_s` |
| 9 | Harness replay + datasets | 🟡 En curso | JSONL e `.mp4` replay; fixtures mínimas activas; falta captura de datasets reales y Git LFS |
| 10 | Robustez de enlace (watchdog de link, degradación en vivo) | ⏳ | HIL unplug test |
| 11 | Heartbeat timeout/read timeout cableados | ⏳ | runtime.toml sin settings muertos |
| 12–14 | — | ⏳ | — |
| 15/16 | Consistency formalizado como gate de release | ⏳ | — |
| Futuro | Comportamiento por eventos e intentos estructurados | 📄 Diseñado | ADR, shadow mode, replay y métricas antes de cualquier control |

## Fuera del alcance de v0.3.0

- **Inteligencia conversacional / LLM / STT / TTS** — laboratorio ADR-0007
  (OFF por defecto). Investigación hecha (memoria, intents estructurados),
  cero código estable.
- **ROS2** — no se implementa hasta que el robot tenga cuello/brazos/audio
  (ADR-0001; seam documentado: `EyeTransport`).
- **Modalidades nuevas (audio, brazos)** — nuevos slots de registry +
  protocolo con límites estrictos por hardware.

## Decisiones registradas

- `src/sirah/transport/` (huérfano, Stage 1) se queda hasta Stage 8,
  cuando se decida su papel (decisión del director, 2026-08-09).
- Percepción real (OpenCV + YuNet) llega DESPUÉS de los contratos y las
  fuentes fake/replay (base de instalación sin dependencias, ADR-0006).
- Los informes de investigación/auditoría (directorio local `informes/`)
  no se versionan en el repo; sus decisiones viven en ADRs y en este
  roadmap.
- La arquitectura futura de comportamiento/LLM está documentada en
  `docs/behavior-llm-architecture.md`; no añade dependencias ni autoridad física.
