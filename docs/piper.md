# Piper TTS local

Estado: experimental e implementado como integración local. La síntesis y la
reproducción reales se validaron en una configuración Debian concreta; esto no
constituye compatibilidad universal ni soporte certificado.

La consola conserva el fake como proveedor predeterminado. Piper se habilita
explícitamente y degrada a conversación textual si falta el ejecutable, modelo,
configuración opcional, reproductor o directorio temporal utilizable:

```bash
.venv/bin/python examples/interactive_conversation.py \
  --speech-provider piper \
  --piper-bin /ruta/a/piper \
  --piper-model /ruta/a/voz.onnx \
  --audio-player pw-play
```

También se admiten `SIRAH_PIPER_BIN`, `SIRAH_PIPER_MODEL`,
`SIRAH_PIPER_CONFIG` y `SIRAH_AUDIO_PLAYER`. SIRAH no lee `.env`, no descarga
modelos y no incluye voces en la distribución. `--audio-player` recibe el
ejecutable; integraciones programáticas pueden proporcionar una tupla
`player_argv` previamente tokenizada.

`/voz-estado` muestra disponibilidad, actividad y estado seguro.
`/voz-detener` cancela la operación actual. `/voz-fin` existe exclusivamente
para el fake y nunca simula la terminación de Piper. El proceso Piper recibe el
texto por stdin; ni argv ni nombres temporales contienen el texto.

Piper y el reproductor (`pw-play` o `aplay`) son dependencias externas. Que los
archivos y ejecutables parezcan disponibles no valida compatibilidad del modelo,
dispositivo, volumen, latencia ni altavoz físico.

## Smoke opt-in

El smoke no forma parte de pytest normal:

```bash
SIRAH_RUN_PIPER_SMOKE=1 \
SIRAH_PIPER_BIN=/ruta/a/piper \
SIRAH_PIPER_MODEL=/ruta/a/voz.onnx \
SIRAH_AUDIO_PLAYER=pw-play \
.venv/bin/python examples/piper_smoke.py
```

Usa una frase fija, aplica timeouts, cierra el adaptador y verifica que no quede
un WAV. No descarga ni instala nada.

## Validación local conocida

Validación realizada el 2026-07-25:

- Debian 13 (trixie), Python 3.13.5 del entorno del proyecto y
  `piper-tts` 1.4.2;
- instalación externa de Piper bajo
  `~/.local/share/sirah-tools/piper/venv/`;
- voz `es_MX-ald-medium`, con el modelo `es_MX-ald-medium.onnx` y su
  configuración `es_MX-ald-medium.onnx.json`, ambos externos al repositorio;
- `/usr/bin/pw-play` como reproductor de SIRAH, con PipeWire y WirePlumber
  activos;
- `/usr/bin/aplay` comprobado también como reproductor manual alternativo.

### Prueba manual

Piper recibió texto mediante stdin y produjo un archivo RIFF/WAVE PCM de 16
bits, mono, 22050 Hz y tamaño mayor que cero. El mismo WAV se reprodujo
correctamente con `/usr/bin/pw-play` y `/usr/bin/aplay`.

### Smoke de SIRAH

Se ejecutó el smoke opt-in con el ejecutable, modelo y configuración externos:

```bash
SIRAH_RUN_PIPER_SMOKE=1 \
SIRAH_PIPER_BIN=<ejecutable-externo> \
SIRAH_PIPER_MODEL=<modelo-externo> \
SIRAH_PIPER_CONFIG=<configuracion-externa> \
SIRAH_AUDIO_PLAYER=/usr/bin/pw-play \
.venv/bin/python examples/piper_smoke.py
```

La salida terminal fue `TERMINAL: completed; playback_completed` y el código de
salida fue 0. Tras el smoke no quedaron WAV del proceso en `/tmp`, ni WAV, PCM
o modelos ONNX dentro del repositorio. Tampoco quedaron procesos `piper`,
`pw-play` o `aplay`, y la consola cerró normalmente.

La consola se inició con el proveedor Piper real. `/voz-estado` informó
`VOZ: disponible=True; activo=False; estado=idle`; `/voz-detener` sin una
operación activa informó `Voz detenida: False.`. El cierre fue normal y no dejó
procesos residuales.

### Alcance y limitaciones

Esta evidencia comprueba en esa máquina la síntesis local real, la reproducción
local real, el smoke integrado de SIRAH, la limpieza del WAV temporal, el cierre
sin procesos residuales y la configuración Debian/PipeWire descrita. La
implementación del runtime y esta compatibilidad local comprobada son hechos
distintos de ofrecer compatibilidad universal.

No se validaron otros sistemas operativos, Raspberry Pi, otras voces ni todo
hardware de audio. Tampoco se comprobaron cancelación física durante la
reproducción, control de descendientes arbitrarios, streaming, múltiples voces
concurrentes, Vosk ni STT. Piper, su entorno, la voz y el reproductor continúan
siendo dependencias externas opcionales: no forman parte de la instalación base
de SIRAH y ningún modelo se guarda en Git.
