# Contribuir a SIRAH

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana**. Gracias por
contribuir a los ojos, el runtime o el laboratorio conversacional.

## Reglas básicas

1. **Prueba antes de pedir review**: `pytest -q` debe pasar completo.
2. **Nunca rompas el contrato**: el protocolo v1.0 es una gramática
   cerrada; cualquier cambio requiere ADR y bump de versión del protocolo
   (`docs/components/protocol.md`, corpus golden de 91 casos).
3. **Disciplina ADR**: las decisiones de arquitectura se registran en
   `docs/adr/` antes o junto con el código que las implementa.
4. **Firmware = autoridad física**: el runtime refleja
   `calibration.h`/`pins.h`; no dupliques constantes (test de
   consistencia).
5. **Conversación aislada**: STT, LLM, TTS y audio no pueden enviar comandos a
   ojos, ESP32 o servos. El contrato de acción permanece en `none`.
6. **Privacidad**: no subas claves, archivos `.env`, audio, PCM,
   transcripciones, prompts, respuestas, fotos identificables ni logs de
   sesiones con texto.
7. **Estilo**: `ruff check .` y `mypy src` limpios.

## Flujo de trabajo

```bash
uv sync --extra cli --extra serial --extra dev
uv run pytest -q
uv run ruff check .
uv run mypy
make -C firmware/sirah-eyes/tests/host core_tests
```

Commits en formato Conventional Commits (`feat(runtime):`, `fix(hardware):`,
`docs:`, `test:`...). El gate de CI corre lint, contract y unit.

Para cambiar conversación, instala los extras y prueba primero sin dispositivos:

```bash
uv sync --extra audio --extra vad --extra conversation --extra edge-tts --extra dev
uv run pytest tests/unit/audio tests/unit/conversation tests/unit/cli -q
uv run sirah-conversation replay tests/fixtures/conversation/approved.jsonl
```

Las pruebas `--live` requieren autorización explícita del operador, pueden
enviar la transcripción final a proveedores cloud y no son requisito de CI. Usa
`config/conversation.env.example` como plantilla; el archivo real vive fuera
del repositorio en `~/.config/sirah/conversation.env` con permisos `0600`.

## Cambios de conversación

Antes de modificar VAD, STT, Ollama, TTS o PortAudio:

1. Conserva los contratos `SpeechToText`, `IntentProposal`, `OperationTTS` y
   `OperationPCMPlayer`, o documenta el cambio con un ADR.
2. Mantén las colas acotadas y la cancelación por operación; el audio obsoleto
   no debe llegar a la bocina después de un barge-in.
3. Añade una prueba que reproduzca el fallo o comportamiento nuevo antes de
   cambiar producción.
4. Para cambios de latencia, registra la línea base de
   `docs/laboratory/voice-latency-baseline.md` sin incluir texto privado.
5. Para PortAudio, prueba interrupción durante reproducción en hardware antes
   de afirmar que el cierre es seguro.

## Hardware

Sin módulo físico, toda verificación se hace con el twin
`FakeESP32` (`--fake`) y tests; la evidencia física VERIFIED se registra
en `docs/hardware/pin-map.md` con fecha, y gana sobre cualquier
contradicción futura.
