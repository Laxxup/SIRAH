# Hoja de ruta de SIRAH v0.3.1

SIRAH significa **Sistema Inteligente Robótico de Asistencia Humana**. Esta es
la situación de los ojos, el laboratorio conversacional y el trabajo posterior.

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
| 8b | Visión en vivo: instrumentación de cámara (fps/dropped/edad de frame), percepción multi-cara, atención anti-flicker, arbitraje de ojos y estado del mundo | Completado | `sirah-perceive`, `AttentionManager`, `EyeArbiter`, `WorldState` y `--attention` en el runtime |
| 9 | Laboratorio conversacional con VAD, STT, LLM, TTS y medición de latencia | Experimental validado en software y laboratorio | `sirah-conversation`, 401 pruebas, `docs/conversation.md` y protocolo de laboratorio |
| 9b | M8.1: visión en vivo estructurada → `WorldState` → contexto conversacional | Completado en software; validación física pendiente | `VisionPipeline`, `VisionContextProvider`, `sirah-conversation vision-chat` y pruebas unit/integración |

## En curso y próximo trabajo

| Etapa | Objetivo | Estado actual | Criterio para cerrarla |
|---|---|---|---|
| 10 | Reproducción de sesiones y conjuntos de datos | En curso | Ya hay JSONL, reproducción de `.mp4` y fixtures mínimos; faltan capturas reales y Git LFS |
| 11 | Supervisión del enlace y degradación en ejecución | Pendiente | Prueba HIL desconectando el enlace |
| 12 | Métricas comparables de conversación y evaluación de TTS incremental | En investigación | Línea base de 30 turnos, p50/p95, calidad de STT y prueba de barge-in |
| 13–15 | Pendiente de definición | Pendiente | — |
| Futuro | Música, navegación y acciones físicas | Diseñado, no implementado | Requiere contratos separados, reproducción autorizada, AEC y revisión de seguridad |

## Límites de v0.3.1

- La conversación, los LLM, STT y TTS son un laboratorio opt-in. La ruta cloud
  puede enviar la transcripción final a Groq y Ollama; no guarda audio ni texto
  por defecto y no controla hardware.
- No hay cancelación de eco acústico. El barge-in es experimental y debe
  validarse con la bocina y micrófono del despliegue final.
- Música, YouTube Music, Spotify y control de reproductores no forman parte de
  esta versión. La API de YouTube permite metadatos, no un servicio oficial de
  streaming de YouTube Music para este caso.
- ROS2 queda para cuando el robot incorpore cuello, brazos y audio. La unión
  prevista con el runtime actual es `EyeTransport` (ADR-0001).
- Audio, brazos y otras modalidades requerirán nuevos componentes de registro y
  un protocolo con límites de seguridad definidos para su hardware.

## Decisiones que condicionan el camino

- `src/sirah/transport/` era un paquete vacío sin uso; se eliminó en la
  consolidación del 2026-08-18. Si un transporte distinto del serial llega a
  hacer falta, se creará donde corresponda (con su ADR).
- La cámara física con OpenCV y YuNet se incorporará después de validar los
  contratos y las fuentes fake o de reproducción. La instalación base no exige
  OpenCV ni el modelo; véase ADR-0006. `sirah-perceive` permite observar la
  cámara/detector sin armar ojos ni abrir el serial (ADR-0009).
- La atención (`--attention`), el arbitraje de ojos y el estado del mundo son
  capacidades de la etapa 8b: opt-in y deterministas; la línea base sigue
  funcionando igual sin ellas.
- La validación física (cámara real + modelo YuNet + foco) y la medición de
  equilibrio productor/consumidor en Raspberry Pi quedan pendientes de
  hardware; los contadores `CameraStats` están listos para ello.
- El corte M8.1 (visión estructurada → conversación) está completo en software
  y cubierto por pruebas con fakes, pero la validación física con cámara real,
  personas en movimiento y chat con Ollama sigue pendiente de hardware.
- Los informes de investigación y auditoría del directorio local `informes/`
  no se guardan en el repositorio. Las decisiones se documentan en los ADR y en
  esta hoja de ruta.
- La arquitectura futura de comportamiento y LLM está en
  `docs/behavior-llm-architecture.md`; no añade dependencias ni autoridad sobre
  el hardware.
- `PerceptionSnapshot` marca el límite semántico para eventos y modo sombra.
  Los frames sin procesar permanecen fuera del dominio de comportamiento.
