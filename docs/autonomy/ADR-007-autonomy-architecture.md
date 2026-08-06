# ADR-007: Autonomous Behavior Architecture

**Estado:** Accepted
**Fecha:** 2026-08-05
**Autores:** SIRAH v2 development

## Contexto

SIRAH v2 tiene conversación reactiva (usuario habla → SIRAH responde). 
Para ser un verdadero robot social, SIRAH necesita autonomía: 
comportamientos que se ejecutan sin intervención humana.

Estudiamos 4 proyectos de referencia:
- EVA Robot (proactivo, afectivo, wakeface)
- InMoov ROS2 (visión + voz + servos, comportamientos reactivos)
- HumanoidOS (HAL, simulación, control en tiempo real)
- diffdrive_esp32 (protocolo serial, PID en MCU)

## Decisión

Implementar una **capa de autonomía** (`src/sirah/autonomy/`) con 3 componentes:

1. **PersonTracker** — Reconocer y diferenciar personas por embedding facial
2. **MoodEngine** — Estado emocional interno con transiciones
3. **IdleBehavior** — Comportamientos cuando no hay interacción

Integrar todo en un **AutonomousCoordinator** que extiende `SituationalCoordinator`.

### Arquitectura

```
AutonomousCoordinator (extiende SituationalCoordinator)
├── PersonTracker
│   ├── detectar rostros (MediaPipe)
│   ├── generar embedding facial
│   └── comparar con DB local → identificar persona
├── MoodEngine
│   ├── estado: HAPPY | NEUTRAL | CURIOUS | TIRED | CONCERNED
│   ├── transiciones basadas en eventos
│   └── modifica prompt del LLM
└── IdleBehavior
    ├── sin nadie × 60s → comentarios ambientales
    ├── persona nueva → saludo
    └── persona conocida → check-in personalizado
```

### Consecuencias

- **Positivo:** SIRAH deja de ser solo reactiva
- **Positivo:** Arquitectura modular — cada componente es independiente y testeable
- **Positivo:** Inspirada en proyectos reales funcionando (EVA, InMoov)
- **Negativo:** Requiere MediaPipe FaceMesh para embeddings (más pesado que FaceDetection)
- **Negativo:** Sin cámara/hardware, todo corre en modo simulado

## Referencias

- EVA Robot: https://github.com/Laura-VFA/Affective-Proactive-EVA-Robot
- InMoov ROS2: https://github.com/aalonsopuig/Inmoov_ROS2
- Research notes: `docs/research/eva-robot-analysis.md`, `docs/research/inmoov-ros2-analysis.md`
