# Piper TTS local

Estado: experimental, implementado como integración local; audio físico no
validado.

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
