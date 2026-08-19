# SIRAH v0.3.1 — Arquitectura

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana** (only in
Spanish, never translated). This document describes the architecture of the
runtime físico y del laboratorio conversacional: capas, límites, dirección de
dependencias y fronteras físicas.

## 1. Sistemas separados

SIRAH mantiene dos sistemas con límites explícitos:

- El runtime físico controla ojos mediante el protocolo PC ↔ ESP32.
- El laboratorio conversacional recibe y genera audio, pero su contrato de
  acción sigue limitado a `none`; no envía comandos al runtime físico.

## 2. Runtime físico

```
 percepción (Stage 8)                   webcam USB → camera_source → face_detector
                                        instrumentada: fps · dropped · frame_age
              ↓ GazeTarget(s) (multi-face)
 atención (visión en vivo)              AttentionManager → primario estable (anti-flicker)
              ↓ GazeTarget (x, y, conf)
 comportamiento (Stage 8)               gaze_behavior → Setpoint + LostFacePolicy
              ↓ Setpoint (normalizado)
 arbitraje (visión en vivo)             EyeArbiter → SAFETY > MANUAL > face_tracking
              ↓ Setpoint otorgado
 runtime estable (PC / Raspberry Pi)    RuntimeApp (lifecycle + registry) ·
                                        EyeLinkSupervisor · SetpointGate · WorldState
              ↓ comandos v1.0 (TARGET / BLINK / HEARTBEAT / STATUS / ERR)
 transporte                             EyeTransport (contrato, ADR-0002)
              ↓ serial (o twin in-memory)
 firmware ESP32 (sirah-eyes)            protocol · mapping · easing · blink_fsm ·
                                        watchdog · limits (calibration.h)
              ↓ I2C + PWM
 hardware                               PCA9685 (0x40) → 6 servos (eye X/Y, 4 párpados)
```

Dependency direction is always toward stable layers: `cli → runtime →
(config, hardware)` and `hardware → protocol + config`; `protocol/`,
`runtime/policies.py` and `transport.py` have zero external dependencies.

## 3. Frontera estable runtime ↔ ESP32

| | Runtime (PC) | ESP32 firmware (sirah-eyes) |
|---|---|---|
| Owns | perception y behavior (Stage 8), policies de seguridad, lifecycle, heartbeat | limits, symmetry, easing, watchdog, blink autónomo, PCA9685 → servos |
| Never | opera fuera de los límites de `calibration.h`/`actuators.yaml` (gate + firmware, defensa en profundidad); decide personalidad (lab ADR-0007) | — |

- PC↔ESP32 = un único transporte, hoy serial (ADR-0002); `EyeTransport`
  permite TCP/BLE/ROS2 sin rediseñar el runtime (ADR-0001).
- El firmware es la AUTORIDAD física (`calibration.h`) y el espejo
  `config/actuators.yaml` está fijado por test de consistencia
  (`sirah-calibrate --validate`); los canales PCA9685 lo están también
  (`pins.h` ↔ `channels`).
- Laboratorio (ADR-0007): `laboratory/` no importa ni es importado por el
  runtime; acceso físico SOLO vía `LabProposalGate`, OFF por defecto.

## 4. Detalles del runtime físico

- `RuntimeApp.from_config` fusiona `runtime.toml` (A9) + `actuators.yaml`.
- Arranque: `_start_eyes()` (transport.connect, falla → DEGRADED, la app
  sigue viva) y `_start_camera()` (mismo patrón, Stage 8).
- Detención limpia: `stop` Event → cancel de tasks → teardown.
- Pipeline (Stage 8 + visión en vivo): `_pipeline_tick` recorre
  frame → detect → atención → behavior → arbitraje → gate → TARGET. La
  detección multi-cara (`MultiFaceDetector`) OBSERVA cada cara y la
  atención elige un primario estable; sin atención, el camino clásico de
  detector único sigue intacto.
- `EyeArbiter` arbitra cada tick entre productores con prioridad
  SAFETY > MANUAL > face_tracking > idle; un productor manual o de
  seguridad puede tomar los ojos aunque el rostro esté en silencio. El
  cable permanece quieto si el setpoint otorgado no cambió (gate de
  último envío) y el firmware suaviza el movimiento físico.
- `WorldState` es una instantánea inmutable por tick (rostro presente,
  objetivo atendido, frescura del frame, setpoint otorgado, percepción
  disponible) construida con `WorldStateBuilder`; es de solo lectura para
  los consumidores.
- `sirah-perceive` es el CLI de diagnóstico: cámara → detector sin armar
  ojos ni abrir el serial; núcleo `perceive()` probado con fakes.

### 4.1 Percepción de gestos (M5)

```
cámara USB (una sola, ADR-0013) → FrameBroker (último frame por suscriptor)
        ├─ suscriptor percepción (YuNet → atención → behavior)
        └─ suscriptor gestos → GestureWorker (hilo único, off asyncio)
                → MediaPipe GestureRecognizer VIDEO → GestureDetection
                → EvidenceHub (gestos) → eventos confirm/release
```

- `GestureWorker` (single-thread) corre la inferencia FUERA del loop de
  asyncio con `run_in_executor`; consume el último frame del broker, no
  encola backlog. Un fallo de MediaPipe aísla el worker sin tumbar la ruta
  de YuNet ni el runtime.
- SIRAH convierte BGR → SRGB contiguo (`np.ascontiguousarray`) y entrega a
  MediaPipe un `mp.Image` (`recognize_for_video`, modo VIDEO). MediaPipe NO
  acepta arrays numpy crudos en este modo.
- Allowlist SIRAH: `Open_Palm`, `Thumb_Up`, `Thumb_Down`, `Victory`. Solo
  gestos allowlist generan observaciones/estado; cualquier otra categoría
  aparece únicamente como `raw` diagnóstico (nunca autoridad).

#### Coordenadas / espejo / handedness (M5.1)

- **No hay espejo en el núcleo**: la imagen se procesa tal como sale de la
  cámara, sin voltear. El preview conserva la misma orientación de la cámara
  que percibe el núcleo; si se añade espejo en la UI, será únicamente
  presentación, nunca en la ruta de percepción.
- **Handedness de MediaPipe asume entrada tipo selfie (espejada)**: la
  clasificación Left/Right asume que la imagen está volteada horizontalmente.
  Como SIRAH NO espeja, las etiquetas `Left`/`Right` de MediaPipe deben
  interpretarse como "lado reportado por el modelo", no como lado anatómico
  del usuario. En el preview se muestran tal cual; si una política futura
  necesitara el lado anatómico, el mapeo se haría en la capa de
  comportamiento, no en percepción, y se documentaría aquí.
- Las coordenadas de `Landmark` se entregan sin normalizar/espejar; cualquier
  mapeo a actuadores (ojos/cabeza) queda en capas posteriores y NO puede
  provenir de percepción cruda (ADR-0014).

## 5. Laboratorio conversacional

```
micrófono → SoundDeviceAudioSource → Silero VAD local
          → turno cerrado PCM 16 kHz mono
          → STT: Faster-Whisper local o Groq Whisper cloud
          → ConversationCore → Ollama Cloud o respuestas locales
          → validación externa: intent, emotion, action=none, speech
          → TTS: Kokoro local, Azure PCM o Edge TTS streaming
          → reproducción PCM → bocina
```

- La captura usa colas acotadas y descarta audio antiguo al saturarse; `--lab`
  reporta descartes y ocupación máxima.
- Edge TTS entrega MP3 incrementalmente, `ffmpeg` lo convierte a PCM y un
  propietario único serializa el ciclo de vida del stream PortAudio.
- Cada turno puede cancelarse por parada o barge-in. No hay AEC, por lo que el
  barge-in sigue siendo experimental.
- Los diagnósticos de latencia no guardan audio ni texto: miden fin de voz, STT,
  Ollama, primer PCM y reproducción. La sonda de Ollama mide primer contenido y
  razonamiento sin retener la respuesta.
- `SIRAH_OLLAMA_THINK=low` es una configuración de laboratorio para reducir
  razonamiento del endpoint. No altera la validación ni autoriza acciones.

## 6. Simulación y pruebas

| Suite | Contenido | Gate |
|---|---|---|
| tests/unit | runtime · config · hardware · policies · percepción · atención · arbitraje — 498 en verde hoy | CI siempre |
| tests/contract | corpus golden 91 casos, parser Python ↔ C++ | CI |
| tests/integration | E2E offline (fake camera → detector → behavior → gate → FakeESP32 → STATE) | CI (desde Stage 8) |
| tests/replay | datasets grabados (driver a crear; LFS) | CI |
| tests/hil | loopback pty + hardware real | SIRAH_HIL=1, fuera de CI |

`FakeESP32` es un twin conductual verificado (ADR-0009/0010): espeja
mapping/easing/blink con las mismas constantes y calibración que el
runtime — probar sin hardware no es un mock improvisado.

## 7. Decisiones arquitectónicas relevantes

- ADR-0001: núcleo ROS2-agnóstico; bridge solo si el robot crece (cuello/
  brazos/audio). No se implementa ahora.
- ADR-0003: un único protocolo de cable cerrado v1.0.
- ADR-0004: comportamientos dueños del firmware; el PC jamás direcciona
  servos.
- ADR-0007: laboratorio de inteligencia separado, OFF por defecto, sin
  autoridad sobre servos y sin componente "SIRAH Cortex".
- ADR-0009: calibración en config; las herramientas no abren el serial.
- ADR-0010: estrategia fake/replay/HIL.
- ADR-0011: PCA9685 + fuente externa 5 V para el rail de servos; canales
  VERIFIED 2026-08-09.
- ADR-0012: atención/arbitraje/world-state como capas deterministas opt-in
  sobre la cadena percepción→comportamiento.
- ADR-0013: una sola cámara dueña del runtime; `FrameBroker` reparte el
  último frame a percepción, telepresencia y VLM sin colas ni backlog
  (investigación de telepresencia).
- La conversación, incluidos STT, LLM, TTS y reproducción, permanece aislada
  del runtime físico hasta una decisión explícita y pruebas de seguridad.
