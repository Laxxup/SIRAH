# Changelog

La evolución anterior a este repositorio se resume en
[`docs/history.md`](docs/history.md). No se asignan versiones retrospectivas a
la etapa del prototipo experimental.

## [Unreleased]

### Added

- Ningún cambio todavía.

### Changed

- Ningún cambio todavía.

### Planned

- Validación segura con un servo real y transporte Serial.
- Voz, visión, contexto avanzado e integración multimodal.
- Robustecimiento de seguridad, privacidad y observabilidad.

## [0.1.0.dev0]

Primera distribución pre-alpha local, sin fecha de publicación ni promesa de
estabilidad.

### Added

- Catálogo y política para `robot.home`, `robot.stop` y `arm.greet`
  provisional.
- Ejecución mediante SIRAH Cortex `0.1.0a1` y un `RobotPort` simulado.
- Contexto presente acotado, únicamente en memoria.
- Contrato estructurado de inteligencia y fake offline.
- Adaptador textual Gemini opcional, con esquema estricto y reintentos
  limitados.
- Ejemplos offline y smoke Gemini opt-in.
- Historia del proyecto y reglas para recuperar conocimiento heredado.

### Changed

- Límites documentados para impedir migraciones automáticas de código heredado.
- Roadmap actualizado con la integración pre-alpha comprobada.

### Planned

- Servo real, Serial, voz, visión, contexto avanzado e integración multimodal.
