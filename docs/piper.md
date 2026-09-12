# Piper TTS

SIRAH usa la distribución mantenida [`OHF-Voice/piper1-gpl`](https://github.com/OHF-Voice/piper1-gpl), fijada en `piper-tts==1.7.0` y publicada como GPL-3.0-or-later.

Piper es necesario **solo para el modo de voz** (`-voice`). El modo de conversación por texto no requiere ni inicializa Piper.

## Setup

Usa Python 3.11 o posterior para los scripts del repositorio que emplean `tomllib`:

```sh
python3 -m venv .venv-piper
.venv-piper/bin/pip install piper-tts==1.7.0
```

Este comando fija `piper-tts`, pero no constituye un lock con hashes de sus dependencias transitivas.

## Modelo de voz

SIRAH espera un modelo de voz compatible con Piper 1.7.0 compuesto por dos archivos:

- `modelo.onnx` — la red neuronal
- `modelo.onnx.json` — metadatos, incluyendo `audio.sample_rate`

Coloca ambos archivos en `models/voices/`:

```text
models/voices/<tu-voz>.onnx
models/voices/<tu-voz>.onnx.json
```

Configura `PIPER_COMMAND` (por ejemplo `.venv-piper/bin/python`) y apunta `PIPER_MODEL` en `.env` al archivo `.onnx`.

El repositorio no incluye modelos de voz ni registra su procedencia ni checksum, porque cada voz tiene su propia licencia y el autor no ha verificado una fuente redistribuible para la voz de ejemplo. Antes de desplegar, confirma que el modelo funciona con Piper 1.7.0 y revisa su licencia.

## Verificación

El benchmark aislado escribe un WAV y reporta latencia de carga/síntesis, real-time factor, CPU time y memoria del proceso:

```sh
.venv-piper/bin/python scripts/benchmark_piper.py \
  --model models/voices/<tu-voz>.onnx \
  --output /tmp/sirah-voz.wav
```

Reproduce el WAV con `aplay` o `ffplay` para evaluar pronunciación y calidad.

## Integración

El runtime de SIRAH carga un proceso de voz al iniciar el modo `-voice` y envía peticiones por stdin. El bridge local (`scripts/piper_server.py`) delimita el PCM por longitud y lo escribe a un proceso `aplay` persistente.

Si falta el comando de Python, el script bridge, el modelo o su `.json`, el arranque del modo voz falla con un mensaje claro.
