# Changelog

## [Unreleased]

### Added

- Web Lab experimental con cámara MJPEG, conversación, cámara móvil, estados de
  ánimo y grabación de voz desde el navegador.
- Preparación de audio WebM a WAV mediante `ffmpeg` antes de Whisper y pruebas
  de regresión para el contrato multimodal del prompt.
- Diagnóstico Web Lab del micrófono mediante `arecord` y exposición de mensajes
  autónomos en la interfaz web.
- Assets del Web Lab incluidos dentro del wheel/sdist, arranque sin cámara para
  pruebas y diagnóstico estructurado de componentes en `/api/status`.
- Clasificación visual BGR/HSV que separa grises de colores saturados, ROI de
  sonrisa proporcional al rostro e histéresis de dos observaciones.
- Percepción multirostro: análisis por persona, colores de ropa distinguibles,
  orden izquierda-derecha y resumen de cantidad de personas para el prompt.
- MediaPipe Tasks opcional para blendshapes de sonrisa y conteo local de dedos,
  con fallback Haar, histéresis por rostro, conteo estable de personas y regla
  de no inventar manos u objetos ausentes.
- Web Lab rediseñado como consola de percepción accesible, con overlay canvas
  opcional de cajas MediaPipe, bboxes de manos, contexto textual visible para
  Groq y actualización de manos en cada tick de análisis.
- Refresco visual inmediato antes de respuestas web, ausencia de rostro sticky,
  actualización configurable de expresiones y ROI robusta de ropa por persona,
  visible en el overlay como rectángulo de muestreo.
- Validación defensiva de `EdgeMessage.from_json` para rechazar payloads y tipos
  inválidos antes de que lleguen al bridge.
- Entrada local Vosk push-to-talk con captura PCM `arecord` cancelable,
  importación tardía, límites defensivos y smoke opt-in.
- Turnos semidúplex INPUT/OUTPUT mediante lease correlacionado y polling no
  bloqueante en la consola.
- Adaptador TTS local experimental para Piper CLI y reproductor administrados,
  con cancelación, timeouts, WAV efímero, polling correlacionado y degradación.
- Comandos de consola para estado y cancelación de voz, guía operativa, ADR y
  smoke Piper opt-in.

### Changed

- El prompt dinámico de `MoodEngine` conserva las capacidades de cámara,
  micrófono y parlantes; la grabación web espera `onstop` antes de enviar el
  audio para evitar blobs vacíos.
- La captura de cámara del Web Lab ahora usa un loop asyncio persistente y el
  stream MJPEG solo emite frames nuevos; se eliminaron intervalos dependientes
  de peticiones HTTP.
- La investigación de `awesome-ros2` se convirtió en patrones locales de QA,
  diagnósticos y límites de protocolo sin introducir ROS 2 ni duplicar Cortex.
- Piper conserva atómicamente la primera causa terminal y la captura arecord
  mantiene cleanup acotado incluso ante fallos de procesos, selector o streams.
- La captura arecord traduce fallos de `poll()` y la consola conserva el modo
  texto ante argumentos o recursos Vosk inválidos.
- Ownership único y esperas acotadas para cleanup de STT, arecord y Piper.
- Validación local real de Piper 1.4.2 en Debian 13 con la voz
  `es_MX-ald-medium`, reproducción mediante PipeWire, smoke de integración
  completado y limpieza sin WAV ni procesos residuales; la evidencia no implica
  compatibilidad universal.
- El circuito situacional se dividió en interacción, simulación, voz, comandos
  locales y composición de runtime. La memoria social ahora expira, se poda y
  confirma saludos al finalizar el TTS simulado.
- El contrato de voz separa estado operacional de resultado terminal y usa
  `operation_id`; `PendingSpeech` ya no conserva el texto hablado.
- Matrices adversariales repetibles cubren first-cause-wins, cleanup excepcional,
  stop vocal integrado, semidúplex y degradación de consola sin esperas reales.

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
