# Entrada local Vosk push-to-talk

Estado: Evidencia histórica de un adaptador experimental; no forma parte del
contrato `sirah-runtime` actual.

La consola actual es un cliente del runtime y no puede activar Vosk, elegir un
modelo ni configurar captura. El runtime-service actual no ofrece un comando de
despliegue para Vosk.

El modelo y `arecord` son externos. SIRAH no descarga ni empaqueta modelos. La
disponibilidad solo comprueba configuración, ejecutable, dependencia y modelo
legible; no garantiza micrófono, routing ni calidad.

La captura histórica era PCM raw mono `S16_LE`, acotada y semidúplex con TTS.

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

No hay smoke Vosk soportado por el runtime-service actual.

El micrófono, routing ALSA, calidad, latencia y comportamiento físico de
cancelación no se han validado. Tampoco existen wake word, AEC, manos libres,
escucha continua ni identificación de hablante.
