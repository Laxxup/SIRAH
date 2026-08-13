# Privacy

Do not commit camera captures, raw audio, transcripts, prompts, responses or
derived user profiles. The conversational prototype keeps its context in RAM
and does not persist audio or transcripts.

Cloud conversation is opt-in. Before using a live command, the operator must
know that the final transcript can be sent to the configured provider. Do not
send frames, sensors, serial commands or hardware configuration to the model.
The hands-free VAD loop never sends continuous or discarded audio to Cloud.
Groq STT receives solo el turno WAV cerrado cuando se selecciona; Ollama recibe
la transcripción final y contexto temporal; Edge TTS receives the validated
reply text. Revisa los términos de cada proveedor antes de una demostración.
Local Kokoro TTS receives only the response text in process memory. It sends no
text or audio to a provider and does not write generated PCM to disk.

Diagnostic session files are opt-in. `--record-session` stores events and
metrics only; `--include-text` also stores text for debugging after an explicit
warning. Session JSONL files use mode `0600` outside the repository. Terminal
scrollback is outside SIRAH's retention controls.

Camera work remains outside the conversational prototype. Obtain consent before
recording or publishing identifiable people. Any future persistence requires a
documented retention period, deletion method and operator controls.

Las métricas de `--lab` y `ollama-stream-probe` están diseñadas para no imprimir
contenido de respuestas. Aun así, la terminal y los servicios cloud son parte
del entorno del operador, no mecanismos de retención de SIRAH.
