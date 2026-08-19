# Laboratorio conversacional v0.3.1

SIRAH incluye un laboratorio conversacional experimental separado del runtime
ocular. Puede escuchar un turno, reconocerlo, generar una respuesta validada y
hablarla; no controla ojos, ESP32, servos, música ni otro hardware físico.

La personalidad de demostración presenta a SIRAH como una anfitriona robótica
cálida y honesta, proyecto del Instituto Tecnológico de Ciudad Madero (ITCM),
desarrollado por una persona en colaboración con el equipo de robótica del Tec.
Puede explicar que conversa por voz y que sus
capacidades visuales siguen en desarrollo, sin afirmar reconocimiento de
personas, seguimiento facial ni control de objetos. Mantiene los últimos seis
intercambios completos solo durante la sesión activa y no conserva recuerdos
entre ejecuciones. Cuando alguien quiere conocer, probar o colaborar con el
proyecto, comparte `github.com/Laxxup/SIRAH`.

## Capacidades y límites

| Capacidad | Estado |
|---|---|
| Conversación manos libres con VAD local | Experimental |
| STT local Faster-Whisper | Disponible como alternativa local |
| STT cloud Groq Whisper | Experimental, opt-in |
| LLM Ollama local o cloud | Experimental, opt-in |
| TTS Kokoro, Azure o Edge | Experimental |
| Edge TTS con primer PCM streaming | Validado en laboratorio |
| Métricas de latencia `--lab` | Disponible |
| Barge-in | Experimental, sin AEC |
| Control de ojos, ESP32 o servos | No implementado |
| Música, YouTube Music, Spotify o reproductores | No implementado |

## Instalación

Python 3.12 es obligatorio. Instala lo necesario según la ruta elegida.

La reproducción de audio usa `sounddevice`, que necesita PortAudio en el
sistema. En Linux (incluidas Raspberry Pi) instálalo antes:

```bash
sudo apt install libportaudio2
```

Ruta local con Faster-Whisper y Kokoro:

```bash
pip install -e ".[audio,vad,conversation,local-tts]"
```

Ruta cloud medida en laboratorio con Groq y Edge:

```bash
pip install -e ".[audio,vad,conversation,edge-tts]"
sudo apt install ffmpeg
```

Silero VAD usa la distribución oficial y su backend ONNX. Faster-Whisper usa
CPU con `int8` por defecto. El modelo `base` se guarda fuera del repositorio en
`~/.cache/sirah/whisper`, o en la ruta de `SIRAH_WHISPER_CACHE`.

La voz local requiere `espeak-ng` disponible en el sistema. Kokoro funciona en
CPU y Python 3.12. La primera carga descarga los pesos; después trabaja sin red
si la caché ya está completa.

## Inicio recomendado: cloud con métricas

1. Crea el archivo privado desde la plantilla:

```bash
mkdir -p ~/.config/sirah
cp config/conversation.env.example ~/.config/sirah/conversation.env
chmod 600 ~/.config/sirah/conversation.env
```

2. Edita el archivo y completa `SIRAH_OLLAMA_HOST`,
`SIRAH_OLLAMA_MODEL`, `SIRAH_OLLAMA_API_KEY` cuando el host remoto lo requiera,
y `SIRAH_GROQ_API_KEY`. Para la configuración de latencia probada, usa:

```text
SIRAH_STT_PROVIDER=groq
SIRAH_TTS_PROVIDER=edge
SIRAH_OLLAMA_THINK=low
```

3. Carga el archivo y arranca:

```bash
set -a
source ~/.config/sirah/conversation.env
set +a
sirah-conversation listen --live --stt-provider groq --tts-provider edge --lab
```

`SIRAH_OLLAMA_THINK=low` es una opción de laboratorio: compara al menos diez
turnos con `default` antes de adoptarla en otro entorno.

## Comandos

```bash
sirah-conversation devices
sirah-conversation replay tests/fixtures/conversation/approved.jsonl
sirah-conversation config
sirah-conversation ollama-check
sirah-conversation ollama-stream-probe --live --think low
```

`replay` es completamente offline: usa transcripciones de fixture, Ollama falso,
TTS falso y reproduccion falsa. No abre dispositivos ni envia datos.

Los comandos con `--live` pueden abrir un microfono o enviar una transcripcion
al proveedor configurado. El operador debe ejecutarlos de forma explicita:

```bash
sirah-conversation ollama-check --live
sirah-conversation text-chat --live
sirah-conversation vision-chat --live --camera-device 0 --yunet-model <ruta> [--gesture-model <ruta>] [--person-model <ruta>]
sirah-conversation push-to-talk --live --text-only --duration 5
sirah-conversation tts-check --live --provider local
sirah-conversation logs list
```

`vision-chat` es un chat de texto cloud anclado en visión en vivo: la cámara,
el rostro YuNet y los modelos opcionales de gesto/persona alimentan la
evidencia, y el contexto de cada turno antepone un resumen compacto en español
(personas presentes con etiquetas temporales, rostro visible y gestos
permitidos). Si la visión no está disponible o caducó, el LLM responde sin
afirmar lo que no ve.

## Modo manos libres

El modo principal es una sesión continua, iniciada una sola vez. Por defecto
usa la voz local:

```bash
sirah-conversation listen --live
```

Para usar Groq Whisper Cloud en vez de Faster-Whisper local, crea una clave en
<https://console.groq.com/keys> y guárdala solo en
`~/.config/sirah/conversation.env`:

```bash
SIRAH_STT_PROVIDER=groq
SIRAH_GROQ_API_KEY=tu_clave
```

Luego inicia la conversación con `--stt-provider groq`. Groq recibe cada turno
cerrado de audio como WAV mono de 16 kHz; nunca se guarda audio en el repositorio.
Faster-Whisper sigue disponible con `--stt-provider local` como respaldo.

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

Para medir la latencia real sin guardar texto ni audio, añade `--lab`:

```bash
sirah-conversation listen --live --stt-provider groq --tts-provider edge --lab
```

La terminal muestra la hora y duración acumulada de cada etapa: cierre de voz,
STT, Ollama, síntesis, inicio de altavoz y fin de reproducción. Para aislar
solo TTS, reproduce una frase de prueba:

```bash
sirah-conversation tts-check --live --provider edge --lab
```

Compara el valor `turno` de `Altavoz: iniciando` entre pruebas. La mejora
porcentual se calcula como `(referencia_ms - prueba_ms) / referencia_ms * 100`.
Los diagnósticos se imprimen únicamente en la terminal; usa `--record-session`
si también quieres guardar eventos de sesión autorizados.

Si una propuesta cloud no llega a TTS, `--lab` indica `Respuesta: silenciosa`.
Cuando la respuesta se descarta por formato, validación o proveedor, imprime
solo la categoría de excepción bajo `diagnóstico:`; nunca el texto de la
transcripción ni la respuesta.

Para investigar solo Ollama Cloud sin micrófono ni texto de respuesta, usa:

```bash
sirah-conversation ollama-stream-probe --live --context-limit 0
```

Imprime tiempos de primer evento, primer fragmento de contenido y respuesta
final, junto con contadores de tokens y de razonamiento que el servidor
entregue. Para comparar modelos con razonamiento, añade `--think false` o
`--think low`; `default` conserva el comportamiento del endpoint.

Para evaluar `low` en la conversación real sin tocar el comando, establece
`SIRAH_OLLAMA_THINK=low` en el archivo privado de configuración. Mantén
`default` como referencia y compara al menos diez turnos de cada condición.

El protocolo de línea base y estrés para la computadora de laboratorio está en
[`docs/laboratory/voice-latency-baseline.md`](laboratory/voice-latency-baseline.md).

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

## Voz Edge

Edge TTS usa las voces neuronales de Microsoft sin configurar una clave Azure.
Instala el extra y `ffmpeg` para usarlo:

```bash
pip install -e ".[audio,conversation,edge-tts]"
sudo apt install ffmpeg
```

Con `--tts-provider edge`, SIRAH entrega a `ffmpeg` los fragmentos recibidos y
reproduce PCM desde un único flujo de salida. No espera a descargar ni a
decodificar el turno completo antes de empezar a hablar. El búfer del sistema
de audio se configura inicialmente en 300 ms para priorizar continuidad. Esa
configuración no se expone todavía como opción del CLI ni variable de entorno.

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

Para conversación cloud, crea tu archivo privado a partir de la plantilla:

```bash
mkdir -p ~/.config/sirah
cp config/conversation.env.example ~/.config/sirah/conversation.env
chmod 600 ~/.config/sirah/conversation.env
```

Edita `~/.config/sirah/conversation.env`, añade las claves y carga las
variables antes de ejecutar el CLI:

```bash
set -a
source ~/.config/sirah/conversation.env
set +a
sirah-conversation listen --live --stt-provider groq --tts-provider edge --lab
```

El CLI no carga ese archivo de forma automática: se mantiene explícito para no
leer ni exponer claves sin autorización del operador.

```text
SIRAH_OLLAMA_HOST=http://127.0.0.1:11434
SIRAH_OLLAMA_MODEL=gpt-oss:20b-cloud
SIRAH_OLLAMA_API_KEY=              # solo para host remoto directo
SIRAH_OLLAMA_THINK=default         # default, false o low
SIRAH_WHISPER_MODEL=base
SIRAH_WHISPER_DEVICE=cpu
SIRAH_WHISPER_COMPUTE_TYPE=int8
SIRAH_WHISPER_LANGUAGE=es
SIRAH_WHISPER_CACHE=~/.cache/sirah/whisper
SIRAH_STT_PROVIDER=local
SIRAH_GROQ_API_KEY=
SIRAH_TTS_PROVIDER=local            # local, azure o edge
SIRAH_EDGE_TTS_VOICE=es-MX-DaliaNeural
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

YouTube Data API permite buscar metadatos de videos y playlists, pero no es una
API oficial de reproducción de YouTube Music para este laboratorio. No uses
extractores no oficiales de audio como parte de SIRAH. Una futura integración de
música requerirá un reproductor autorizado, controles de pausa/ducking y AEC
para no degradar VAD, STT ni barge-in.
