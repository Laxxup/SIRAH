# ADR-005: Piper CLI como primer TTS local real

## Estado

Aceptado como integración experimental de pre-alpha. No validado físicamente.

## Contexto y decisión

SIRAH necesita confirmar un saludo únicamente después de audio reproducido, sin
convertir TTS en `RobotPort` ni introducir una dependencia Python obligatoria.
Se ejecutan Piper CLI y un reproductor local como procesos directos
administrados. Los modelos permanecen externos.

Se elige CLI/subprocess frente a una biblioteca Python porque Piper ya ofrece
un límite ejecutable pequeño, aislable y opcional. `player_argv` es una tupla
tokenizada y validada; nunca se interpreta una cadena de shell. Los procesos
usan listas, `shell=False`, stderr descartado de forma acotada y texto UTF-8 por
stdin.

El adaptador acepta una sola operación y usa un worker dedicado, sin cola,
`asyncio` global ni callbacks. El consumidor hace polling no bloqueante. Esto
mantiene `InteractionMemory` en el thread coordinador y vuelve explícita la
entrega exactamente una vez.

`SpeechState` representa solo `IDLE`, `SYNTHESIZING`, `PLAYING`,
`CANCELLING` y `CLOSED`; `SpeechOutcome` representa el terminal. Cada aceptación
crea un `operation_id`, única correlación. `stop(expected_operation_id)` impide
que una cancelación vieja alcance una operación nueva.

Síntesis, reproducción y terminación tienen deadlines monotónicos separados.
Al cancelar o vencer un deadline se solicita `terminate`, se espera un grace
acotado, se usa `kill` si hace falta y se hace `wait` final. SIRAH garantiza el
proceso directo que inicia; no promete terminar descendientes arbitrarios ni
crea grupos POSIX.

Cada operación usa un WAV aleatorio con permisos restrictivos, cerrado antes de
entregarlo a otro proceso y eliminado en `finally`. `close` es idempotente,
cancela y espera a que el worker quede recolectado; la terminación de cada
proceso directo usa el grace acotado descrito arriba. Los fallos se reducen a
razones breves sin stderr, texto ni rutas privadas.

La disponibilidad solo comprueba ejecutables resolubles, archivos legibles y
temporales utilizables. No afirma compatibilidad del modelo ni audio físico. La
consola continúa por texto cuando Piper está degradado; el fake sigue siendo el
default.

## Alternativas y consecuencias

Callbacks habrían permitido que el worker tocara coordinación o memoria;
streaming y colas ampliarían concurrencia y superficie de cancelación. Una
biblioteca Python añadiría acoplamiento y empaquetado sin necesidad actual.
Descartar stderr pierde diagnóstico detallado, pero evita bloqueo, acumulación
y exposición; podrá reemplazarse por captura estrictamente acotada si existe un
caso operativo comprobado.

Revisar esta decisión si se requiere streaming medido, múltiples voces,
sincronización labial, diagnóstico acotado más rico, soporte no POSIX o si la
API estable de Piper ofrece una integración más segura que el proceso CLI.
