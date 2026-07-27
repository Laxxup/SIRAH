# Entrada local Vosk push-to-talk

Estado: Experimental. Validación: simulación; micrófono físico no validado.

La consola conserva texto como modo predeterminado. Vosk se activa explícitamente:

```bash
python -m pip install ".[stt-vosk]"
.venv/bin/python examples/interactive_conversation.py \
  --speech-input-provider vosk --vosk-model /ruta/al/modelo
```

El modelo y `arecord` son externos. SIRAH no descarga ni empaqueta modelos. La
disponibilidad solo comprueba configuración, ejecutable, dependencia y modelo
legible; no garantiza micrófono, routing ni calidad.

`/escuchar` inicia PTT, `/escuchar-finalizar` solicita el cierre,
`/escuchar-cancelar` cancela y `/escucha-estado` consulta el estado. La captura
es PCM raw mono `S16_LE`, acotada y semidúplex con TTS.

`SpeechInputRuntime` es el único propietario de `capture.stop`, finalización
del reconocedor y commit terminal. Cancelar solo registra intención; el worker
resuelve cancelación, finalize, timeout, EOF o fallo mediante first-cause-wins,
limpia y libera INPUT. `ArecordPcmCapture` asigna cada proceso a un único actor
de recolección.

El audio se procesa en memoria por fragmentos y nunca se persiste. Parciales y
JSON de Vosk tampoco se registran. Una transcripción FINAL ordinaria entra en el
contexto efímero existente; un stop exacto se consume localmente antes del
contexto y de Gemini.

La consola hace polling con selector POSIX y timeout corto: puede observar un
terminal STT sin esperar otra línea de texto y no usa un loop ocupado. El
reconocedor limita parciales, texto final y segmentos, rechaza JSON o
confidence inválidos y reinicia su estado después de fallos.

El smoke manual requiere `SIRAH_RUN_VOSK_SMOKE=1`, `SIRAH_VOSK_MODEL`, stdin
TTY y opcionalmente `SIRAH_ARECORD_BIN`, `SIRAH_AUDIO_INPUT_DEVICE` y
`SIRAH_VOSK_SMOKE_SHOW_TEXT=1`. No forma parte de la suite normal.

El micrófono, routing ALSA, calidad, latencia y comportamiento físico de
cancelación no se han validado. Tampoco existen wake word, AEC, manos libres,
escucha continua ni identificación de hablante.
