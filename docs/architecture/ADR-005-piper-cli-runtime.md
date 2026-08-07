# ADR-005: Piper API persistente como TTS local real

## Estado

Aceptado como integración experimental de pre-alpha. No validado físicamente.

## Contexto y decisión

SIRAH necesita confirmar un saludo únicamente después de audio reproducido, sin
convertir TTS en `RobotPort` ni introducir una dependencia Python obligatoria.
El runtime carga la API Python de Piper una vez y usa un reproductor local
separado para cada WAV efímero. Los modelos permanecen externos.

Se elige la API `piper-tts` frente al CLI para eliminar descubrimiento ambiguo y
carga repetida del modelo. La síntesis vive en un worker de hilo breve para no
bloquear asyncio; la reproducción sigue separada y solo recibe el WAV temporal
por la salida que el servicio validó. Piper nunca recibe texto por argv.

El adaptador acepta una sola operación, sin cola ni callbacks. El consumidor
conserva el lease semidúplex existente, manteniendo `InteractionMemory` fuera del
worker y haciendo explícita la entrega exactamente una vez.

`SpeechState` representa solo `IDLE`, `SYNTHESIZING`, `PLAYING`,
`CANCELLING` y `CLOSED`; `SpeechOutcome` representa el terminal. Cada aceptación
crea un `operation_id`, única correlación. `stop(expected_operation_id)` impide
que una cancelación vieja alcance una operación nueva.

La carga y la síntesis fallan con errores de voz tipados. El fallo de Piper
degrada el componente de voz; no detiene el proceso ni la conversación textual.
La reproducción informa su fallo como resultado terminal no exitoso para que el
lease se libere.

Cada operación usa un WAV aleatorio, cerrado antes de entregarlo al reproductor
Los fallos se reducen a razones breves sin texto ni rutas privadas.

La disponibilidad refleja que el modelo está cargado y no ha fallado; la
configuración comprueba archivos legibles, no compatibilidad del modelo ni audio
físico. La consola continúa por texto cuando Piper está degradado; el fake sigue
siendo el default.

## Alternativas y consecuencias

El CLI requería descubrimiento de binarios y cargaba el modelo por operación.
Streaming y colas ampliarían concurrencia y superficie de cancelación. El
adaptador no conserva stderr, texto ni WAV después de una operación.

Revisar esta decisión si se requiere streaming medido, múltiples voces,
sincronización labial, diagnóstico acotado más rico o soporte no POSIX.
