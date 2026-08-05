# Instrucciones para agentes de SIRAH v2

SIRAH es el agente robótico conversacional con percepción visual y voz async.
Depende de SIRAH Cortex (`WorldState`, seguridad, `ActionExecutor`, `RobotPort`).
Nunca modifiques Cortex ni dupliques sus modelos públicos.

## Antes de editar

Lee `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/`, las ADR, el módulo
afectado, sus pruebas y la consola. Revisa la API pública de Cortex.

## Reglas de arquitectura v2

- Usa el `WorldState` de Cortex; no construyas una segunda copia.
- Toda capacidad mecánica atraviesa `CapabilityPolicy` → Cortex → `ActionExecutor` → `RobotPort`.
- Groq/Ollama solo propone decisiones estructuradas; nunca crea `RobotCommand` ni toca hardware.
- Percepción (MediaPipe) corre en Pi 4B o simulada; emite `PerceptionFrame` inmutable.
- STT (faster-whisper) y TTS (Piper/gTTS) usan sus contracts asíncronos.
- `AudioTurnCoordinator` es semiduplex con leases async.
- `build_system(profile=...)` es el ÚNICO factory; no crees instancias sueltas.
- Todo es asíncrono (`asyncio`); usa `pytest-asyncio` en tests.
- Imports pesados (aiohttp, numpy, mediapipe, cv2) son lazy. No dependencias eager.
- Errores tipados: `SirahError → SirahFatalError | SirahRecoverableError → subclases`.
- Fakes deterministas para testing: `FakeIntelligence`, `SimulatedPerception`, `FakeSpeechInput`, `FakeSpeechOutput`, `SimulatedRobot`.

## Estructura de capas

```
sirah/
├── errors.py, types.py          Fundamentos
├── core/         orchestrator, context, registry
├── intelligence/ port, groq, ollama, fake, demo
├── perception/   port, face_detector, pose_detector, webcam, simulated
├── voice/        ports, whisper_stt, piper_tts, gtts_tts, mic, coordinator, simulated
├── action/       capabilities, runner, commands, simulated
├── social/       memory, initiative, situational
├── bridge/       protocol, pi_server, laptop_client, serial_esp32, mqtt
├── factory.py    build_system(profile)
└── console.py    Consola interactiva
```

## Verificación

```bash
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy src tests --ignore-missing-imports
.venv/bin/python -m pytest -q
.venv/bin/python -m build
git diff --check
```

La suite no usa red, Groq real, secretos, `time.sleep` ni hardware.

## Cambios y seguridad

No guardes conversaciones, claves ni prompts completos. No hagas push, force
push, merge, tag, release ni operaciones remotas sin autorización explícita.
Actualiza documentación, pruebas y CHANGELOG con cada responsabilidad real.
