# Prototipo conversacional

SIRAH incluye una base conversacional experimental separada del runtime ocular.
No controla ojos, ESP32, servos ni otro hardware fisico.

## Instalacion

Python 3.12 es obligatorio. Instala los extras para captura, Faster-Whisper,
Silero VAD y conversación:

```bash
pip install -e ".[audio,vad,conversation]"
```

Silero VAD usa la distribución oficial y su backend ONNX. Faster-Whisper usa
CPU con `int8` por defecto. El modelo `base` se guarda fuera del repositorio en
`~/.cache/sirah/whisper`, o en la ruta de `SIRAH_WHISPER_CACHE`.

## Comandos

```bash
sirah-conversation devices
sirah-conversation replay tests/fixtures/conversation/approved.jsonl
sirah-conversation config
sirah-conversation ollama-check
```

`replay` es completamente offline: usa transcripciones de fixture, Ollama falso,
TTS falso y reproduccion falsa. No abre dispositivos ni envia datos.

Los comandos con `--live` pueden abrir un microfono o enviar una transcripcion
al proveedor configurado. El operador debe ejecutarlos de forma explicita:

```bash
sirah-conversation ollama-check --live
sirah-conversation text-chat --live
sirah-conversation push-to-talk --live --text-only --duration 5
sirah-conversation tts-check --live
```

## Modo manos libres

El modo principal es una sesion continua, iniciada una sola vez:

```bash
sirah-conversation listen --live
```

Para preparar la prueba sin Azure, TTS ni bocina, usa el modo de texto:

```bash
SIRAH_OLLAMA_HOST=http://127.0.0.1:11434 \
SIRAH_OLLAMA_MODEL=gpt-oss:20b-cloud \
sirah-conversation listen --live --text-only
```

Muestra `escuchando`, `procesando`, `hablando`, `interrumpido`,
`recuperandose` y `detenido`. Usa Silero VAD local para abrir y cerrar cada
turno. `Ctrl-C` detiene la captura, cancela el trabajo pendiente y libera los
buffers. `push-to-talk` queda como diagnostico, alternativa de accesibilidad y
fallback cuando VAD no este disponible.

El microfono se analiza continuamente solo en memoria. Solo se transcribe un
turno cerrado y solo una transcripcion final no vacia se envia al LLM. Los
fragmentos cortos, ruido y silencio se descartan localmente.

La primera version usa umbrales mas estrictos y una ventana de confirmacion
para una nueva voz durante TTS. Esto reduce disparos falsos, pero no sustituye
la cancelacion de eco acustico: SIRAH no puede distinguir perfectamente al
usuario de su propia voz sin AEC real.

`push-to-talk` queda para diagnostico, accesibilidad y como fallback. La prueba
manual pendiente requiere confirmar micrófono, bocina y comportamiento acústico.
No se ha verificado la calidad de transcripción con voz humana.

## Configuracion

```text
SIRAH_OLLAMA_HOST=http://127.0.0.1:11434
SIRAH_OLLAMA_MODEL=gpt-oss:20b-cloud
SIRAH_OLLAMA_API_KEY=              # solo para host remoto directo
SIRAH_WHISPER_MODEL=base
SIRAH_WHISPER_DEVICE=cpu
SIRAH_WHISPER_COMPUTE_TYPE=int8
SIRAH_WHISPER_LANGUAGE=es
SIRAH_WHISPER_CACHE=~/.cache/sirah/whisper
SIRAH_AZURE_SPEECH_KEY=
SIRAH_AZURE_SPEECH_REGION=
SIRAH_AZURE_TTS_VOICE=es-MX-DaliaNeural
SIRAH_VAD_THRESHOLD=0.5
SIRAH_VAD_MIN_SPEECH_MS=250
SIRAH_VAD_END_SILENCE_MS=700
SIRAH_VAD_MAX_TURN_SECONDS=15
SIRAH_VAD_PRE_ROLL_MS=300
```

El daemon local puede gestionar la autenticacion de modelos Cloud. No definas
una API key para `127.0.0.1` salvo que tu instalacion la requiera.

## Limites

Ollama Cloud no garantiza structured outputs. SIRAH pide JSON por prompt y
valida externamente intent, emotion, action y speech. Una salida invalida se
convierte en silencio seguro. El contexto vive solo en RAM; no se guardan
audio, transcripciones, perfiles ni prompts.

Azure TTS es opcional. Sin `--text-only`, configura
`SIRAH_AZURE_SPEECH_KEY` y `SIRAH_AZURE_SPEECH_REGION`. La voz
`es-MX-DaliaNeural` sigue pendiente de prueba auditiva y medición de latencia.
