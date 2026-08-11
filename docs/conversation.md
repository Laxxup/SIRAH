# Prototipo conversacional

SIRAH incluye una base conversacional experimental separada del runtime ocular.
No controla ojos, ESP32, servos ni otro hardware fisico.

## Instalacion

Python 3.12 es obligatorio. Instala los extras para captura, Faster-Whisper,
Silero VAD, conversación y voz local:

```bash
pip install -e ".[audio,vad,conversation,local-tts]"
```

Silero VAD usa la distribución oficial y su backend ONNX. Faster-Whisper usa
CPU con `int8` por defecto. El modelo `base` se guarda fuera del repositorio en
`~/.cache/sirah/whisper`, o en la ruta de `SIRAH_WHISPER_CACHE`.

La voz local requiere `espeak-ng` disponible en el sistema. Kokoro funciona en
CPU y Python 3.12. La primera carga descarga los pesos; después trabaja sin red
si la caché ya está completa.

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
sirah-conversation tts-check --live --provider local
sirah-conversation logs list
```

## Modo manos libres

El modo principal es una sesión continua, iniciada una sola vez. Por defecto
usa la voz local:

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

El modo predeterminado es semidúplex: mientras SIRAH reproduce una respuesta,
descarta frames del micrófono y aplica una guarda corta antes de volver a VAD.
`--barge-in` es experimental y muestra una advertencia porque no hay AEC.

`push-to-talk` queda para diagnostico, accesibilidad y como fallback. La prueba
manual pendiente requiere confirmar micrófono, bocina y comportamiento acústico.
No se ha verificado la calidad de transcripción con voz humana.

## Voz local

SIRAH usa [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) con la voz
española femenina `ef_dora`. El motor `kokoro`, los pesos y el repositorio del
modelo están bajo Apache-2.0. Kokoro genera PCM mono de 24 kHz en memoria y el
reproductor usa esa misma frecuencia.

La voz se descarga desde el repositorio oficial a
`~/.cache/sirah/kokoro`, o a `SIRAH_LOCAL_TTS_CACHE`. No se versiona ni se
guarda audio generado. Piper se evaluó y no se adoptó: su motor oficial actual
es GPL-3.0 y las fichas es_MX revisadas no identifican una voz femenina.

Prueba la voz antes de abrir el micrófono:

```bash
SIRAH_LOCAL_TTS_CACHE="$HOME/.cache/sirah/kokoro" \
sirah-conversation tts-check --live --provider local
```

Debe reproducir: `Hola, soy SIRAH. Mi voz local está funcionando.`

Para conversación completa:

```bash
SIRAH_OLLAMA_HOST=http://127.0.0.1:11434 \
SIRAH_OLLAMA_MODEL=gpt-oss:20b-cloud \
SIRAH_LOCAL_TTS_CACHE="$HOME/.cache/sirah/kokoro" \
sirah-conversation listen --live --tts-provider local \
  --input-device "Default Source" --sample-rate 16000
```

La primera síntesis tarda por la descarga y carga del modelo. Kokoro expone
generación por fragmentos, pero esta integración entrega el turno terminado a
la cola PCM. Cancelar un turno evita que PCM obsoleto llegue al altavoz; no
interrumpe una inferencia de CPU que ya está dentro de una llamada de biblioteca.
No hay medición todavía en Raspberry Pi 4 de 8 GB.

## Sesiones de diagnóstico

Por defecto no se escribe ningún registro. En `text-chat`, `--record-session`
crea un JSONL con eventos y métricas; `--include-text` autoriza incluir la
transcripción y la respuesta. Esta segunda opción muestra un aviso: el archivo
es explícito, pero el scrollback de la terminal también puede conservar texto.

Los archivos viven fuera del repositorio en `$XDG_STATE_HOME/sirah/sessions/`
o `~/.local/state/sirah/sessions/`, con permisos `0600`. Nunca incluyen audio,
PCM, claves, tokens, headers ni variables de entorno.

```bash
sirah-conversation logs list
sirah-conversation logs latest
sirah-conversation logs show latest
sirah-conversation logs diagnose latest
```

Los comandos de borrado solo reconocen identificadores de archivos de sesión
en ese directorio; no aceptan rutas arbitrarias.

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
SIRAH_TTS_PROVIDER=local
SIRAH_LOCAL_TTS_MODEL=hexgrad/Kokoro-82M
SIRAH_LOCAL_TTS_VOICE=ef_dora
SIRAH_LOCAL_TTS_CACHE=~/.cache/sirah/kokoro
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

Azure TTS es opcional. Selecciónalo con `--tts-provider azure` y configura
`SIRAH_AZURE_SPEECH_KEY` y `SIRAH_AZURE_SPEECH_REGION`. La voz
`es-MX-DaliaNeural` sigue pendiente de prueba auditiva y medición de latencia.
