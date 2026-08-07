# Piper TTS local

Estado: experimental e implementado como integración local persistente. La
síntesis y la reproducción reales se validaron en una configuración Debian
concreta; esto no constituye compatibilidad universal ni soporte certificado.

La consola y Web Lab son clientes de `sirah-runtime`. Ningún cliente puede
habilitar Piper, elegir modelo, configuración, reproductor o dispositivo. El
servidor decide exclusivamente los archivos externos y la salida permitida.

Instala `piper-tts` mediante el extra opcional y configura únicamente en el
entorno privado del servicio:

```bash
.venv/bin/python -m pip install ".[voice-piper]"
export SIRAH_RUNTIME_PIPER_MODEL=/ruta/externa/voz.onnx
export SIRAH_RUNTIME_PIPER_CONFIG=/ruta/externa/voz.onnx.json
```

Ambos valores deben referir archivos regulares legibles. SIRAH no lee `.env`, no
descarga modelos y no incluye voces en la distribución. Carga
`piper.voice.PiperVoice` una vez al iniciar el runtime mediante
`PiperVoice.load(model_path, config_path=...)`; no descubre ni invoca el CLI de
Piper.

Para cada turno, `PiperVoice.synthesize_wav()` escribe un WAV temporal. El
reproductor propiedad del runtime ejecuta `aplay -q -D
SIRAH_RUNTIME_OUTPUT_DEVICE <wav>` con una espera acotada; timeout o cancelación
terminan el proceso hijo. `aplay` es una dependencia externa: que el ejecutable
exista no valida compatibilidad del modelo, dispositivo, volumen, latencia ni
altavoz físico.

La síntesis escribe un WAV temporal sin texto en el nombre, lo entrega al
reproductor de runtime para `SIRAH_RUNTIME_OUTPUT_DEVICE` y lo elimina siempre.
Un fallo de carga, síntesis o reproducción marca Piper no saludable; la voz se
degrada sin detener conversación textual ni el runtime.

## Licencia

`piper-tts` es una dependencia opcional GPL. No se distribuye con SIRAH, pero
sus términos y los de cada voz externa aplican al operador y a cualquier
redistribución. Antes de empaquetar, distribuir o combinar SIRAH con
`piper-tts` o una voz, se requiere revisión legal de las obligaciones GPL y de
la licencia específica del modelo. La licencia Apache-2.0 de SIRAH no cambia.

## Verificación

Las pruebas unitarias no cargan modelos ni reproducen audio. Tras configurar el
servicio y confirmar manualmente la salida correcta, el único smoke físico es
explícito:

```bash
SIRAH_RUN_PIPER_PHYSICAL_SMOKE=1 \
.venv/bin/python -m pytest tests/test_piper_physical_smoke.py -q
```

Este comando carga la voz configurada y reproduce una frase fija. No ejecutarlo
en CI ni en un host con una salida no confirmada.

## Validación local conocida

Validación realizada el 2026-07-25:

- Debian 13 (trixie), Python 3.13.5 del entorno del proyecto y
  `piper-tts` 1.4.2;
- instalación externa de Piper bajo
  `~/.local/share/sirah-tools/piper/venv/`;
- voz `es_MX-ald-medium`, con el modelo `es_MX-ald-medium.onnx` y su
  configuración `es_MX-ald-medium.onnx.json`, ambos externos al repositorio;
- `/usr/bin/aplay` como reproductor del runtime, con la salida ALSA configurada.

### Prueba manual

Piper recibió texto por la API Python y produjo un archivo RIFF/WAVE PCM de 16
bits, mono, 22050 Hz y tamaño mayor que cero. El mismo WAV se reprodujo
correctamente con `/usr/bin/aplay`.

### Alcance y limitaciones

Esta evidencia comprueba en esa máquina la síntesis local real, la reproducción
local real y la configuración Debian/PipeWire descrita. La implementación del
runtime y esta compatibilidad local comprobada son hechos distintos de ofrecer
compatibilidad universal.

No se validaron otros sistemas operativos, Raspberry Pi, otras voces ni todo
hardware de audio. Tampoco se comprobaron cancelación física durante la
reproducción, streaming, múltiples voces concurrentes, Vosk ni STT. Piper, su
entorno, la voz y `aplay` continúan siendo dependencias externas opcionales: no
forman parte de la instalación base de SIRAH y ningún modelo se guarda en Git.
