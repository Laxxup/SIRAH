# Changelog

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana** (solo en
español). Histórico de releases. Formato: Conventional Commits.

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

### Robustez y documentación
- `fix(audio)`: propiedad serializada del stream de salida para evitar cerrar
  PortAudio mientras una escritura nativa sigue activa.
- `fix(conversation)`: el buffer de turno conserva hasta 15 segundos de audio
  con bloques de 32 ms, en vez de truncar turnos largos cerca de cuatro segundos.
- `docs`: guía de conversación, plantilla de configuración privada, protocolo
  de laboratorio, documentación de arquitectura, release y contribución.

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
