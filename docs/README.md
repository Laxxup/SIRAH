# Documentación

Índice para navegar `docs/` según lo que buscas. Los documentos normativos
(protocolo, ADR) se mantienen en inglés para conservar la especificación sin
ambigüedad; el resto está en español.

## Empezar

- [Inicio rápido](quickstart.md) — del repositorio a ojos, visión y
  conversación en pasos, con y sin hardware.
- [Conversación](conversation.md) — instalación, configuración privada,
  comandos y diagnóstico del laboratorio de voz.

## Entender

- [Arquitectura](architecture.md) — capas, límites y fronteras físicas entre
  runtime, visión y conversación.
- [Hoja de ruta](roadmap.md) — qué está implementado, en curso y pendiente.
- [ADR](adr/) — decisiones de arquitectura, con índice en `adr/README.md`.

## Hardware

- [Hardware](hardware/) — requisitos, cableado, pin map y validación
  hardware-in-the-loop.
- [Protocolo PC ↔ ESP32](components/protocol.md) — especificación normativa
  v1.0 del canal serial (inglés).
- [Calibración](calibration.md) — cómo actualizar los límites físicos
  (`calibration.h` ↔ `actuators.yaml`).

## Conversación y privacidad

- [Conversación](conversation.md) — guía completa del laboratorio de voz.
- [Privacidad](privacy.md) — qué se envía a proveedores cloud y qué se guarda.

## Desarrollar

- [Desarrollo](development.md) — entorno, extras y descarga de modelos.
- [Pruebas](testing.md) — suites, gates y cómo ejecutarlas.
- [Release](release.md) — prechecks y cierre de una release.
- [Contribución](../CONTRIBUTING.md) — reglas y flujo de trabajo.
- [Laboratorio](laboratory/) — protocolos de medición experimental (latencia
  de voz, evaluación de conversación).

## Histórico

- [Documentos históricos](archive/) — planes y diseños de etapas pasadas.
  **No describen el sistema actual**; solo para reconstruir decisiones
  antiguas.