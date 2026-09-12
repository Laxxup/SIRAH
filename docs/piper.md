# Piper TTS

SIRAH usa la distribucion mantenida
[`OHF-Voice/piper1-gpl`](https://github.com/OHF-Voice/piper1-gpl), fijada en
`piper-tts==1.7.0` y publicada como GPL-3.0-or-later. El runtime carga un
proceso de voz al iniciar y envia
sentence-sized requests over stdin. PCM is length-delimited by the local bridge
and written to a persistent `aplay` process.

## Setup

Para ejecutar tambien los verificadores Python del repositorio que usan
`tomllib`, usa Python 3.11 o posterior. Instala la version directa fijada de
Piper fuera del modulo Go:

```sh
python3 -m venv .venv-piper
.venv-piper/bin/pip install piper-tts==1.7.0
```

Este comando fija `piper-tts`, pero no constituye un lock con hashes de sus
dependencias transitivas.

The voice `.onnx` (+ `.onnx.json` con `audio.sample_rate`) is NOT versioned:
it is ignored by Git. Place your Piper-compatible voice at:

```text
models/voices/<tu-voz>.onnx
models/voices/<tu-voz>.onnx.json
```

Configura `PIPER_COMMAND=.venv-piper/bin/python` y apunta `PIPER_MODEL` en
`.env` al modelo. El ejemplo usa
`models/voices/es_MX-claude-high.onnx`, pero el repositorio no registra la
procedencia ni el checksum de esa voz. Confirma que el modelo funciona con
Piper 1.7.0 y revisa su licencia antes de desplegarlo; los archivos de voz
conservan licencias separadas de la licencia MIT del repositorio. `make check`
no valida la voz porque sus archivos no forman parte del repositorio. El
benchmark aislado escribe un WAV y reporta latencia de carga/sintesis,
real-time factor, CPU time y memoria del proceso:

```sh
.venv-piper/bin/python scripts/benchmark_piper.py \
  --model models/voices/es_MX-claude-high.onnx \
  --output /tmp/sirah-es_MX-claude-high.wav
```

Play the generated WAV locally with `aplay` or `ffplay` to evaluate pronunciation
and voice quality. Candidate voices should still be benchmarked before deployment.

The current runtime requires Piper. If the command, script, model, or metadata
is missing, startup fails clearly instead of falling back to Edge TTS.
