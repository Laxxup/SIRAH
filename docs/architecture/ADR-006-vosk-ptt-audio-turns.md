# ADR-006: Vosk PTT y turnos de audio correlacionados

## Estado

Aceptada para implementación experimental.

## Decisión

Separar adquisición (`PcmCapturePort`), reconocimiento
(`SpeechRecognizerPort`) y operación (`SpeechInputRuntime`). `arecord` se usa
como proceso externo por su interfaz estable y porque evita incorporar una
biblioteca de dispositivo al proceso Python. En POSIX, stdout es no bloqueante
y se lee con selector y `os.read`; no se usa `communicate`.

PCM es mono S16_LE exacto. Un byte impar puede conservarse entre dos lecturas,
pero EOF impar falla. Vosk se importa tarde. Sus `Result()` completos son
segmentos internos acotados; solo `finalize()` produce el único FINAL
operacional. Texto, segmentos y parciales tienen límites.

La interacción inicial es push-to-talk semidúplex. Un
`AudioTurnCoordinator` rechaza, sin cola, reservas simultáneas INPUT/OUTPUT.
Cada reserva produce un lease opaco único con generación; solo el lease vigente
exacto puede liberar el turno.

Toda salida atraviesa `GuardedSpeechOutput`. El adaptador llama
síncronamente el hook de aceptación antes de arrancar un worker y el guard
registra `operation_id -> lease` antes de cualquier terminal. El callback
terminal one-shot libera físicamente, no al hacer poll. El fake expone su
acción de laboratorio mediante un control separado, nunca mediante unwrap.

La entrada coalesce un parcial y conserva un terminal. Cancelación, timeout,
EOF, finalize, close y fallo compiten en una única transición terminal.
Captura se recolecta antes de liberar INPUT. El coordinador superior ejecuta
stop exacto antes de conversación; el resto de FINAL puede entrar al contexto
efímero.

`cancel` solo valida correlación, registra la primera causa y despierta al
worker; nunca detiene captura ni espera procesos en el hilo llamador. Un único
worker posee `capture.stop`, `recognizer.finalize` y el commit terminal. Cada
subprocess de arecord o Piper tiene asimismo un solo actor de cleanup, sin
mantener locks durante `select`, lectura, `wait`, `terminate` o `kill`.

La consola POSIX selecciona stdin con timeout corto y drena terminales STT en
cada tick. Streams sin descriptor usan una ruta determinista para pruebas, sin
reloj real ni `sleep`.

No se persiste PCM, JSON ni transcripción en logs. Modelo y `arecord` permanecen
externos; el extra se llama `stt-vosk`. Se eligió rechazo inmediato frente a
diferir para mantener una sola operación y ninguna cola.

## Revisión futura

Revisar backend nativo, AEC o escucha continua únicamente con requisitos,
hardware, privacidad y pruebas separados. Esta decisión no anuncia wake word,
manos libres, identificación de hablante ni micrófono validado.
