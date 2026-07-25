# Changelog

La evolución anterior a este repositorio se resume en
[`docs/history.md`](docs/history.md). No se asignan versiones retrospectivas a
la etapa del prototipo experimental.

## [Unreleased]

### Added

- Adaptador TTS local experimental para Piper CLI y reproductor administrados,
  con cancelación, timeouts, WAV efímero, polling correlacionado y degradación.
- Comandos de consola para estado y cancelación de voz, guía operativa, ADR y
  smoke Piper opt-in.

### Changed

- El circuito situacional se dividió en interacción, simulación, voz, comandos
  locales y composición de runtime. La memoria social ahora expira, se poda y
  confirma saludos al finalizar el TTS simulado.
- El contrato de voz separa estado operacional de resultado terminal y usa
  `operation_id`; `PendingSpeech` ya no conserva el texto hablado.

### Planned

- Validación segura con un servo real y transporte Serial.
- Voz, visión, contexto avanzado e integración multimodal.
- Robustecimiento de seguridad, privacidad y observabilidad.

## [0.1.0.dev0]

Primera distribución pre-alpha local bajo Apache-2.0, sin fecha de publicación
ni promesa de estabilidad. No es software certificado para seguridad
funcional.

### Added

- Catálogo y política para `robot.home`, `robot.stop` y `arm.greet`
  provisional.
- Ejecución mediante SIRAH Cortex `0.1.0a1` y un `RobotPort` simulado.
- Contexto presente acotado, únicamente en memoria.
- Contrato estructurado de inteligencia y fake offline.
- Adaptador textual Gemini opcional, con esquema estricto y reintentos
  limitados.
- Ejemplos offline y smoke Gemini opt-in.
- SIRAH Laboratory Console con fake por defecto, estado de componentes,
  capacidades habilitadas y snapshot operativo de lectura.
- Comandos locales para estado, componentes, capacidades, contexto, eventos,
  limpieza y cierre.
- Percepción de presencia simulada integrada mediante eventos públicos y
  `WorldState` de Cortex.
- Memoria de interacción, iniciativa de saludo determinista, cooldown, modo
  silencio, autonomía y TTS simulado cancelable.
- Router local prioritario para `stop`, `para` y `detente`.
- Historia del proyecto y reglas para recuperar conocimiento heredado.

### Changed

- Límites documentados para impedir migraciones automáticas de código heredado.
- Roadmap actualizado con la integración pre-alpha comprobada.
- La actualización cierra la demostración pre-alpha `0.1.0.dev0`; no crea un
  tag ni una release.

### Planned

- Servo real, Serial, voz, visión, contexto avanzado e integración multimodal.
