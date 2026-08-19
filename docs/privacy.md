# Privacidad

No se versionan capturas de cámara, audio crudo, transcripciones, prompts,
respuestas ni perfiles derivados de usuarios. El prototipo conversacional
mantiene su contexto en RAM y no persiste audio ni transcripciones.

La conversación cloud es opt-in. Antes de usar un comando `--live`, el
operador debe saber que la transcripción final puede enviarse al proveedor
configurado. No envíes frames, sensores, comandos serie ni configuración de
hardware al modelo. El loop VAD manos libres nunca envía audio continuo ni
descartado a la nube. Groq STT recibe solo el turno WAV cerrado cuando se
selecciona; Ollama recibe la transcripción final y contexto temporal; Edge TTS
recibe el texto validado de la respuesta. Revisa los términos de cada
proveedor antes de una demostración. El Kokoro TTS local recibe únicamente el
texto de la respuesta en memoria del proceso; no envía texto ni audio a ningún
proveedor y no escribe PCM generado en disco.

Los archivos de sesión de diagnóstico son opt-in. `--record-session` guarda
eventos y métricas únicamente; `--include-text` también guarda texto para
depuración tras un aviso explícito. Los JSONL de sesión usan modo `0600`
fuera del repositorio. El scrollback de la terminal queda fuera de los
controles de retención de SIRAH.

El trabajo con cámara permanece fuera del prototipo conversacional. Obtén
consentimiento antes de grabar o publicar personas identificables. Cualquier
persistencia futura requiere un período de retención documentado, un método de
borrado y controles del operador.

Las métricas de `--lab` y `ollama-stream-probe` están diseñadas para no
imprimir contenido de respuestas. Aun así, la terminal y los servicios cloud
son parte del entorno del operador, no mecanismos de retención de SIRAH.