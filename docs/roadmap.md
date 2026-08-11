# Hoja de ruta de SIRAH v0.3.0

SIRAH significa **Sistema Inteligente Robótico de Asistencia Humana**. Esta es
la situación del subsistema ocular: lo terminado, lo que falta para cerrar la
versión y el trabajo que pertenece a fases posteriores.

## Ya disponible

| Etapa | Trabajo realizado | Estado | Evidencia |
|---|---|---|---|
| 1 | Base del monorepo | Completado | ADR-0008 |
| 2 | Especificación del protocolo v1.0 | Completado | `docs/components/protocol.md` |
| 3 | Parsers en Python y C++ con corpus golden de 91 casos | Completado | Doble parser y `test_parsers_contract` en CI |
| 4 | Firmware para seis actuadores, pruebas host y calibración V6.12 | Validado el 2026-08-09 | `firmware/sirah-eyes` y `calibration.h` |
| 5 | Adaptador serie `EyeTransport` | Completado | `serial_adapter.py` y 45 pruebas |
| 6 | Simulador conductual `FakeESP32` | Completado | ADR-0009/0010 y 22 pruebas |
| 7 | Runtime con `asyncio`, registro de componentes, políticas y CLI | Completado | `app.py`, `cli/run.py` y 169 pruebas |
| 8 | Seguimiento 2D con fuente de cámara, detector facial y comportamiento de mirada | Completado | Pipeline cableado, OpenCV/YuNet opcional, E2E offline y `lost_face_center_s` |

## En curso y próximo trabajo

| Etapa | Objetivo | Estado actual | Criterio para cerrarla |
|---|---|---|---|
| 9 | Reproducción de sesiones y conjuntos de datos | En curso | Ya hay JSONL, reproducción de `.mp4` y fixtures mínimos; faltan capturas reales y Git LFS |
| 10 | Supervisión del enlace y degradación en ejecución | Pendiente | Prueba HIL desconectando el enlace |
| 11 | Timeouts de heartbeat y lectura conectados a la configuración | Pendiente | `runtime.toml` sin parámetros sin efecto |
| 12–14 | Pendiente de definición | Pendiente | — |
| 15/16 | Convertir la consistencia en requisito de release | Pendiente | — |
| Futuro | Comportamiento guiado por eventos e intenciones estructuradas | Diseñado | ADR, modo sombra, reproducción y métricas antes de autorizar cualquier control |

## Límites de v0.3.0

- La conversación, los LLM, STT y TTS siguen siendo un laboratorio de
  ADR-0007, desactivado por defecto. Hay investigación sobre memoria e
  intenciones estructuradas, pero no código estable incluido en esta versión.
- ROS2 queda para cuando el robot incorpore cuello, brazos y audio. La unión
  prevista con el runtime actual es `EyeTransport` (ADR-0001).
- Audio, brazos y otras modalidades requerirán nuevos componentes de registro y
  un protocolo con límites de seguridad definidos para su hardware.

## Decisiones que condicionan el camino

- `src/sirah/transport/`, creado en la etapa 1 y sin uso actual, se conserva
  hasta decidir su función tras la etapa 8 (decisión del director, 2026-08-09).
- La cámara física con OpenCV y YuNet se incorporará después de validar los
  contratos y las fuentes fake o de reproducción. La instalación base no exige
  OpenCV ni el modelo; véase ADR-0006.
- Los informes de investigación y auditoría del directorio local `informes/`
  no se guardan en el repositorio. Las decisiones se documentan en los ADR y en
  esta hoja de ruta.
- La arquitectura futura de comportamiento y LLM está en
  `docs/behavior-llm-architecture.md`; no añade dependencias ni autoridad sobre
  el hardware.
- `PerceptionSnapshot` marca el límite semántico para eventos y modo sombra.
  Los frames sin procesar permanecen fuera del dominio de comportamiento.
