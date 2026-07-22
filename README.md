# SIRAH

**Sistema Inteligente Robótico de Asistencia Humana**

SIRAH es el sistema completo del robot: capacidades concretas, dispositivos,
protocolos, firmware, experimentos y documentación de integración. Este
repositorio comienza de forma deliberadamente mínima y crecerá cuando exista
código real que justifique nuevas responsabilidades.

SIRAH Cortex es el núcleo determinista hermano. Posee dominio, eventos,
`WorldState`, comportamiento, planificación, seguridad, ejecución, tracking,
cancelación y emergencia. SIRAH utilizará Cortex; Cortex no dependerá de este
repositorio.

```text
conversación / visión / dispositivos
                │
                ▼
              SIRAH
                │
                ▼
          SIRAH Cortex
                │
                ▼
      RobotPort / adaptadores
                │
                ▼
      ESP32 / firmware / hardware
```

El diagrama es conceptual. El mecanismo técnico entre ambos repositorios
(paquete, Git, IPC, MQTT u otro) sigue pendiente.

## Estado actual

| Área | Estado | Validación | Evidencia local |
|---|---|---|---|
| Saludo Velxio con un servo | Experimental | Validado en simulación | `experiments/velxio/greet_person_preview/` |
| Controlador facial ESP32/PCA9685 | Planeado | No validado | Inventario proporcionado por el equipo |
| ESP32-CAM | Planeado | No validado | Sin implementación local encontrada |
| Conversación (STT/LLM/TTS) | Planeado | No validado | Sin implementación local encontrada |
| Visión y percepción | Planeado | No validado | Contratos genéricos solo en Cortex |

No se encontró evidencia local de firmware estable para siete servos, Gemini,
Vosk, Piper, cámara, MQTT o Serial concreto. No se presentan como
implementados.

## Hardware conocido

El inventario declara un ESP32, un PCA9685 y siete servos faciales. El mapa de
canales conocido está documentado en
[`docs/components/face-controller.md`](docs/components/face-controller.md).
No existe evidencia local de validación física ni calibraciones.

## Navegación

- `docs/architecture/`: decisiones y límites transversales.
- `docs/components/`: inventario comprobable y estado de componentes.
- `experiments/`: prototipos sin promover a integración estable.
- `docs/roadmap.md`: trabajo activo y criterios de promoción.

No existen todavía `src/`, `subsystems/`, `adapters/` ni `firmware/` porque no
hay implementaciones estables que demuestren esas responsabilidades.

## Decisiones abiertas

- forma de integrar SIRAH con Cortex;
- topología de procesos y equipos (PC, Raspberry Pi, ESP32);
- protocolos Serial, MQTT o HTTP;
- estructura de software y lenguajes;
- validación eléctrica, mecánica y de seguridad del controlador facial;
- adquisición y procesamiento de imágenes;
- proveedores y arquitectura de conversación.

