# Changelog

## [Unreleased]

### Added

- Seguidor de ojos físico: script `scripts/eyes_demo.py` y firmware
  `firmware/sirah-eyes/sirah-eyes.ino` hacen que un ESP32 mueva el ojo horizontal
  para seguir la cara detectada por MediaPipe; protocolo serial `X 0-100`, `CENTER`,
  `BLINK`, `READY`. Solo parpadeo es automático; el ojo se mueve solo por comandos y
  se centra cuando no hay nadie.
- Laboratorio de voz `scripts/sirah_voice_lab.py`: ojos + micrófono (C270 `hw:1,0`)
  + Whisper (STT) + inteligencia (Groq si hay `GROQ_API_KEY`, si no eco) + Piper TTS
  en español. SIRAH es **autoconsciente**: su prompt incluye su estado corporal
  (posición del ojo, cara detectada, color de ropa, sonrisa, distancia, luz) y un
  historial reciente para evitar repetir; libertad creativa con personalidad cálida.
- Documentación `docs/como-usar-sirah.md` (cómo lanzar ojos, voz y preview) y
  `docs/components/eyes.md` (protocolo, calibración, integración pendiente).
- `scripts/eyes_live_preview.py`: ventana en vivo con detección de cara;
  `scripts/eye_follow_evidence.py`: log + frames anotados para evidencia;
  `scripts/run_voice_lab.sh`: lanzador desacoplado.

### Changed

- Corrección de geometría de bbox en `src/sirah/perception/mediapipe_vision.py`:
  `_bbox()` devuelve `(x1, y1, x2, y2)` pero `_torso_bbox`, `_face_context` y la
  normalización de `FaceDetection` lo trataban como `(x, y, w, h)`. Se unificó la
  semántica a `(x1, y1, x2, y2)` y se calculan ancho/alto localmente; esto corrige
  la ROI del torso y la detección de colores.
- Clasificador de color en `src/sirah/perception/face_detector.py` más sensible:
  reconoce rojo, naranja, café, amarillo, verde, verde azulado, azul claro, azul,
  azul oscuro, morado, rosa, gris, gris oscuro, negro y blanco en luz interior.
- Micrófono por defecto del laboratorio fijado al de la C270 (`hw:1,0`).

### Fixed

- Normalización incorrecta del bbox de `FaceDetection` (usaba `x2, y2` como ancho y
  alto), que provocaba cajas mal escaladas en modo MediaPipe.

### Added (sesion actual 2026-08-07)

- Laboratorio de voz rapido `scripts/sirah_voice_lab_fast.py`: pipeline con VAD
  (graba hasta que callas, no tiempo fijo), Whisper `tiny` + beam=1 para
  transcripcion rapida en CPU, y `SelfAwareIntelligence` que inyecta el estado
  corporal de SIRAH (face_x, color de ropa, sonrisa, distancia, luz, manos) y un
  historial reciente en el prompt de Groq para conversacion natural sin repetir.
- `scripts/run_voice_lab_fast.sh`: lanzador desacoplado del lab rapido.

### Changed (sesion actual 2026-08-07)

- Whisper default a modelo `tiny` y `beam_size=1` en `src/sirah/voice/stt_whisper.py`
  (transcripcion ~3x mas rapido en CPU, calidad aceptable para conversacion).
- Grabacion por defecto reducida a 3s con VAD que corta al detectar silencio.

### Fixed (sesion actual 2026-08-07)

- Entrada oficial `sirah-runtime`: proceso headless único que crea
  `SirahRuntime`, lee perfil, socket Unix, secretos y allowlists de dispositivos
  solo desde el entorno del servidor, valida la configuración y cierra de forma
  ordenada ante `SIGINT` o `SIGTERM`. Se añadió una plantilla systemd no
  desplegable; no instala, habilita ni inicia ningún servicio.
- El despliegue prepara `sirah-runtime` con Python 3.14 y una unidad Web Lab
  local opcional, sin habilitar ni iniciar servicios. Los secretos del runtime
  (`SIRAH_RUNTIME_*_SECRET`) se separan explícitamente de los secretos de sus
  clientes (`SIRAH_CLI_SECRET` y `SIRAH_WEB_LAB_SECRET`), y la selección de
  salida queda retenida por `DeviceRegistry` para uso futuro del runtime.
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

- Se retiró el descubrimiento ambiguo y la invocación CLI de Piper. Síntesis y
  reproducción quedan separadas bajo ownership del runtime; no se persisten WAV
  ni texto hablado.
- Piper actualiza el componente de voz a degradado ante fallo de carga, síntesis
  o reproducción. `aplay` ahora tiene timeout y cleanup al cancelarse; la guía y
  el aviso de terceros describen únicamente la API Python, `aplay` y la revisión
  legal requerida para la dependencia GPL opcional.
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
- Instalación verificada de SIRAH sobre Raspberry Pi 4B 8GB (Debian 13 trixie,
  aarch64): venv propio, extras Groq/voice/bridge, 204 tests, consola y Web Lab
  operativos; servicio systemd `sirah-web` con autostart en el arranque.
- Percepción validada con Logitech C270 (V4L2 `/dev/video0`) usando cascadas
  Haar; los cascades se descargan automáticamente si el wheel de cv2 no los
  empaqueta (cv2 >=5 eliminó `CascadeClassifier`, por eso SIRAH fija
  `opencv-python-headless>=4.8,<5`).
- `scripts/deploy_pi.sh` reescrito para trixie: nombres de paquetes reales
  (alsa-utils, libcamera solo para CSI), instalación del cerebro completo en la
  Pi, cascades cv2 y creación del servicio systemd.
- Voz por Web Lab desde el micrófono de la Pi: el botón \`Grabar voz\` ya no usa
  \`getUserMedia\` ni requiere HTTPS; dispara \`POST /api/listen\` sin audio para
  que \`MicCapture\` (arecord) grabe en la Pi, y \`/api/listen\` acepta un campo
  \`device\` opcional (por defecto \`default\`). gTTS reproduce por el sink
  WirePlumber (por ejemplo, audífonos Bluetooth A2DP).
- Audio habilitado en la Pi con \`pipewire-alsa\`: ALSA enruta por PipeWire,
  sink Bluetooth ERAZER como salida por defecto y mic de la Webcam C270 como
  única fuente de captura.
- Auditoría de estabilidad: \`handle_text\` del orquestador usaba un
  \`DecisionType.CONVERSATION\` construido dinámicamente (\`type("DT", ...)\`) en
  el fallback ante \`IntelligenceError\`; ahora usa el enum importado, sin
  \`# type: ignore\`.
- \`GTTSTTS.speak\` borra el MP3 temporal tras la reproducción: cada frase filtraba
  un archivo en \`/tmp\` (tmpfs/RAM en la Pi).
- \`GroqIntelligence._call_api\` envuelve respuestas 200 malformadas
  (\`KeyError\`/\`IndexError\`/\`TypeError\`) en \`IntelligenceUnavailableError\` en
  lugar de propagar una excepción no controlada que rompe la petición.
- \`SirahOrchestrator.start\` marca \`READY\` los componentes registrados
  (intelligence/perception/voice/action) para que \`/api/status\` no los reporte
  \`uninitialised\` pese a estar operativos.
- Web Lab: `/api/chat` y `/api/listen` degradan con JSON (504/503) ante timeouts
  o loop asyncio no iniciado; `/api/listen` responde con mensaje controlado si
  `MicCapture.start()` falla (arecord ausente o dispositivo ocupado) en vez de un
  500.
- Auditoría Web Lab: la cámara del celular ahora alimenta de verdad la
  percepción. El loop de captura de `VisionLoop` respeta un modo móvil
  (frames subidos por `/api/upload_frame` con keepalive de 2 s) y deja de
  pisar `_latest_frame` mientras llegan uploads; al elegir cámara laptop
  (`/api/vision`), el modo móvil se desactiva.
- Web Lab: `btn-vision`, `btn-mobile` y `btn-mood` notifican errores en vez de
  fallar en silencio; el humor solo cambia tras confirmar el servidor y se
  re-sincroniza con `/api/status`; el placeholder de cámara restaura su markup
  original al apagar la cámara.
- Web Lab: indicadores honestos — el punto de estado arranca neutro (no verde),
  el badge LIVE se oculta si la visión está inactiva o el servidor no responde,
  y «Mostrar mapeo» arranca desactivado (coherente con `aria-pressed` y el
  mensaje de bienvenida).

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
