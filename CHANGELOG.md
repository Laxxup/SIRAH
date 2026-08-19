# Changelog

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana** (solo en
español). Histórico de releases. Formato: Conventional Commits.

## Unreleased — Visión en vivo (en desarrollo)

### Percepción
- `feat(conversation)`: M8.1.3 — el modo de voz (`sirah-conversation
  listen --live`) puede usar la cámara con el MISMO `VisionPipeline` que
  `vision-chat` (sin arquitectura paralela ni duplicar Evidence/WorldState):
  flags opt-in `--camera-device --yunet-model [--gesture-model
  --person-model]` (cámara y modelo YuNet van juntos) y diagnóstico
  `--log-vision-context`/`--log-gesture-telemetry`; el `ConversationCore`
  del flujo de voz recibe el mismo `VisionContextProvider`, la percepción
  corre en sus propias tareas sin esperar a STT/Ollama/TTS, y Ctrl-C cierra
  micrófono, audio, workers, `FrameBroker` y cámara una sola vez. Sin
  cámara, la conversación por voz funciona exactamente igual que antes.
  (El preview diagnóstico queda fuera de este milestone: sin segunda
  cámara; headless por defecto.)
- `fix(perception)`: M8.1.1/1.2 — la hipótesis de confirmación lenta de gesto
  fue refutada por la medición física (Victory mantenido confirma en ~40 ms,
  inferencia ~40-60 ms, detección continua; muy dentro de la ventana global
  de 0.5 s), así que la adquisición de gestos vuelve a la política global
  anterior y se conserva la telemetría útil: `GestureWorker` expone por feed
  (`GestureTelemetry`: latencia de inferencia, edad de frame, gestos
  allowlisted, candidato X/2, eventos; nunca landmarks ni frames) impresa por
  `sirah-conversation vision-chat --log-gesture-telemetry`.
- `feat(conversation)`: M8.1.2 — telemetría de contexto visual por turno,
  opt-in y solo en cada pregunta: `sirah-conversation vision-chat
  --log-vision-context` imprime, justo antes de enviar cada petición al LLM,
  el bloque de visión exacto inyectado (sin imágenes, landmarks, cajas ni
  payloads; con timestamp monotónico; `visión no disponible` cuando no hay
  grounding visual). El logger observa el valor ya computado por
  `ConversationCore`; no modifica la petición real.
- `feat(perception)`: `Frame.captured_at` (marca de tiempo monotónica de la
  fuente) y `OpenCVCameraSource` instrumentada: `CameraStats` con frames
  capturados/consumidos/descartados, `capture_fps` y edad del último frame;
  semántica de frame más reciente (frescura > procesar cada frame).
- `feat(perception)`: contrato `MultiFaceDetector` + `YuNetFaceDetector.detect_many`
  para observar cada cara; `detect` (mayor cara) sigue siendo compatible.
- `feat(cli)`: `sirah-perceive`, CLI de diagnóstico cámara → detector sin
  armar ojos ni abrir el serial.
- `feat(perception)`: M8.1, corte vertical visión → mundo → conversación:
  `VisionPipeline` (cámara + rostro YuNet + workers opcionales de gesto/persona
  sobre un `FrameBroker` y un `EvidenceHub` compartidos) y
  `VisionContextProvider`; el rostro atendido y las personas rastreadas
  (presencia + quieta/en movimiento) entran a la evidencia con semántica
  corregida (`face`, pista `primary`); `format_vision_context` produce un
  bloque compacto en español (`VISIÓN ACTUAL` + `EVENTOS VISUALES RECIENTES`)
  que nunca expone cajas, landmarks ni nombres de modelo; `WorldState.perception`
  ahora lleva `PerceptionFacts`.

### Comportamiento y runtime
- `feat(behavior)`: `AttentionManager` (atención opt-in): primario estable a
  partir de detecciones multi-cara con histéresis de adquisición/cambio,
  continuidad por proximidad y retención ante pérdida breve (anti-flicker).
- `feat(runtime)`: `EyeArbiter` arbitra los ojos por prioridad
  SAFETY > MANUAL > face_tracking > idle; la cadena frame → detect → atención
  → behavior → arbitraje → gate → TARGET se documenta en `architecture.md`.
- `feat(runtime)`: `WorldState` inmutable por tick (rostro, objetivo, frescura,
  setpoint otorgado, percepción disponible); `RuntimeResult` expone
  `gaze_producer` y `last_frame_age_s`; el cable permanece quieto si el
  setpoint otorgado no cambió.
- `feat(cli)`: `sirah-runtime --attention` activa la atención con fuente de
  cámara o reproducción.

### Conversación
- `feat(conversation)`: `ConversationCore` acepta un proveedor `vision_context`
  y antepone el bloque de visión actual a cada petición cloud sin guardarlo en
  la memoria de turno (la percepción caduca, no se repite como verdad actual).
- `feat(conversation)`: `sirah-conversation vision-chat` — chat de texto cloud
  anclado en visión en vivo (cámara + YuNet + gesto/persona opcionales).
- `feat(conversation)`: el prompt del sistema describe la visión real (personas
  con etiquetas temporales, rostro y gestos permitidos; sin identidad,
  emociones ni objetos) y retira la afirmación de que la visión no existe.

### Límites conocidos
- La visión en vivo requiere OpenCV/YuNet (extra opcional) y aún no se ha
  validado físicamente con cámara real; `CameraStats` mide el equilibrio
  productor/consumidor para la Raspberry Pi.

## v0.3.1 — Laboratorio conversacional y observabilidad (2026-08-13)

### Conversación
- `feat(conversation)`: STT cloud opcional con Groq Whisper para turnos WAV
  mono de 16 kHz, manteniendo Faster-Whisper local como alternativa.
- `feat(conversation)`: Edge TTS opcional con voces neuronales, decodificación
  streaming con `ffmpeg` y salida PCM continua; Azure y Kokoro permanecen
  disponibles.
- `feat(conversation)`: modo `--lab` con marcas de tiempo para fin de voz,
  STT, Ollama, primer PCM, reproducción y salud de la cola de captura.
- `feat(conversation)`: sonda de Ollama streaming que mide primer evento,
  primer contenido, razonamiento y respuesta final sin almacenar contenido.
- `feat(conversation)`: `SIRAH_OLLAMA_THINK=low` permite evaluar un presupuesto
  reducido de razonamiento para Ollama Cloud; su impacto debe compararse en el
  entorno de laboratorio antes de adoptarlo.
- `feat(conversation)`: política de turnos más natural: las charlas sociales
  pasan al modelo, evita preguntas automáticas y comparte GitHub solo ante
  preguntas sobre colaboración, pruebas o construcción.
- `fix(conversation)`: una respuesta de Ollama que no cumple el contrato JSON
  produce una solicitud hablada para repetir, en lugar de silencio.

### Robustez y documentación
- `fix(audio)`: propiedad serializada del stream de salida para evitar cerrar
  PortAudio mientras una escritura nativa sigue activa.
- `fix(conversation)`: el buffer de turno conserva hasta 15 segundos de audio
  con bloques de 32 ms, en vez de truncar turnos largos cerca de cuatro segundos.
- `docs`: guía de conversación, plantilla de configuración privada, protocolo
  de laboratorio, documentación de arquitectura, release y contribución.
- `feat(hardware)`: calibrador PCA9685 con etiquetas de ángulos, perfil temporal
  en NVS y exportación para actualizar la calibración oficial versionada.
- `fix(hardware)`: pruebas de firmware sincronizadas con los ángulos medidos de
  ojos y párpados.
- `docs(hardware)`: guía de diagnóstico, alimentación, Arduino CLI/IDE y
  atribución de la referencia mecánica EyeMech epsilon 3.2 de @WillCogley.

### Límites conocidos
- La conversación sigue siendo experimental, opt-in y no controla hardware.
- No hay AEC: el barge-in es experimental y debe probarse con el micrófono y la
  bocina finales.
- No se integra música, YouTube Music, Spotify ni control de reproductores.

## v0.3.0 — Milestone 1 (eyes core)

### Stage 7 (2026-08-09)
- `feat(runtime)`: runtime asyncio Python ≥ 3.12: `RuntimeApp` (lifecycle
  + registry ready/degraded/off), `HeartbeatWriter`, `SetpointGate`,
  `LostFacePolicy`, `sirah-runtime` CLI (`--fake --eyes`).
- `feat(config)`: loader TOML + env `SIRAH_*`, consistency
  `calibration.h` ↔ `actuators.yaml` (`sirah-calibrate validate`).
- 169 tests en verde; CI ampliado con job `unit`.

### Stage 6 (2026-08-09)
- `feat(hardware)`: FakeESP32 twin conductual (ADR-0009/0010): espeja
  mapping/easing/blink con reloj virtual inyectable. 22 tests.

### Stage 5 (2026-08-09)
- `feat(hardware)`: adapter serial USB-UART (`SerialTransport`,
  `EyeTransport` como contrato, ADR-0002). PTY loopback en scripts/.

### Stage 4 (2026-08-09)
- `feat(firmware)`: core de 6 actuadores (protocol, mapping, easing,
  blink_fsm) + platform (PCA9685, pins.h) + tests host C++.
- Calibración V6.12 VERIFIED físicamente (sweep manual, 2026-08-09);
  `calibration.h` como autoridad.

### Stage 3 (2026-08-08)
- `test`: corpus golden 91 casos + doble parser gateado en CI (Python
  `parse_line.py` ↔ C++ `contract_checker`).

### Stage 2 (2026-08-08)
- `docs`: especificación normativa del protocolo v1.0
  (docs/components/protocol.md, gramática cerrada, ADR-0003).

### Stage 1 (2026-08-08)
- `chore`: skeleton del monorepo, ADRs 0001–0010, LICENSE Apache-2.0.
