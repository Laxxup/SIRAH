# Línea base de voz en laboratorio

Ejecuta estas pruebas en la computadora de laboratorio antes de modificar el
pipeline de Ollama. No guardes claves, audio, transcripciones ni respuestas en
este archivo.

## Preparación

```bash
set -a
source ~/.config/sirah/conversation.env
set +a
sirah-conversation tts-check --live --provider edge --lab
```

Confirma que la terminal muestra `primer PCM listo` y que termina sin advertencias
de `ffmpeg`, `PortAudio` o core dump.

## Conversación

```bash
sirah-conversation listen --live --stt-provider groq --tts-provider edge --lab
```

Realiza 30 turnos normales, diez turnos de 10 a 15 segundos, veinte
interrupciones con Ctrl-C durante reproducción y veinte intentos de barge-in.
Reinicia el proceso después de cada Ctrl-C.

Registra los valores p50, p95 y p99 sin incluir texto conversacional:

| Métrica | p50 ms | p95 ms | p99 ms | Fallos |
|---|---:|---:|---:|---:|
| Fin de voz a STT listo | | | | |
| Ollama inicio a respuesta lista | | | | |
| Edge inicio a primer PCM | | | | |
| Fin de voz a altavoz iniciando | | | | |
| Cancelación a silencio | | | | |

Al finalizar cada ejecución `--lab` reporta los descartes y máximo de la cola
de captura. La condición de aceptación es cero descartes en carga normal y
cero core dumps durante las interrupciones.

## Matriz de VAD y salida

Prueba `SIRAH_VAD_END_SILENCE_MS` en `500`, `650`, `700` y `850`. Conserva el
valor más bajo que no corte frases ni empeore la transcripción. La latencia de
salida usa 300 ms por defecto y no se expone todavía como ajuste; evalúa valores
menores solo si una versión futura incorpora un parámetro para ello y conserva
el menor valor sin clics ni underruns.

## Sonda de streaming Ollama

Esta sonda no inicia micrófono, TTS ni guarda la respuesta; únicamente solicita
una frase corta y muestra métricas de eventos NDJSON. Ejecuta cuatro veces cada
condición para comparar p50 y el peor caso:

```bash
sirah-conversation ollama-stream-probe --live --context-limit 0
sirah-conversation ollama-stream-probe --live --context-limit 4
sirah-conversation ollama-stream-probe --live --context-limit 12
```

La implementación actual no inyecta contexto conversacional en la sonda; el
campo `context_items` etiqueta la condición que se está comparando. Registra
`first_event_ms`, `first_content_ms`, `total_ms`, `request_bytes`,
`prompt_tokens` y `output_tokens`, nunca la respuesta. Si `first_content_ms`
es considerablemente menor que `total_ms`, el siguiente experimento puede
evaluar TTS incremental. Si ambos son similares, la prioridad será reducir el
prefill o cambiar el modelo/endpoint.

Con modelos que generan razonamiento antes del contenido, compara también el
modo predeterminado contra los niveles documentados por Ollama:

```bash
sirah-conversation ollama-stream-probe --live --think default
sirah-conversation ollama-stream-probe --live --think false
sirah-conversation ollama-stream-probe --live --think low
```

Registra `thinking_events` junto a `first_content_ms`. No cambies aún la
conversación real: primero confirma que `--think false` o `--think low` reduce
el p95 de primer contenido sin producir JSON inválido ni respuestas peores.

La muestra inicial descartó `false`: produjo más eventos de razonamiento y una
mediana peor. `low` redujo tokens/eventos, pero requiere diez turnos reales
contra `default`. Para ese A/B, cambia solo esta línea del archivo privado y
reinicia el proceso entre condiciones:

```bash
SIRAH_OLLAMA_THINK=default
# SIRAH_OLLAMA_THINK=low
```
