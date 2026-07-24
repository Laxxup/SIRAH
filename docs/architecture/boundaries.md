# Límites entre SIRAH, Cortex y firmware

## Cortex

Posee comandos y eventos genéricos, `WorldState`, Runtime, planes,
`SafetySupervisor`, `ActionExecutor`, `PlanDispatcher`, `RobotPort`, tracking,
cancelación, emergencia y resultados. No posee canales, ángulos, PWM, GPIO,
calibraciones ni proveedores concretos.

## SIRAH

Posee el catálogo actual de `robot.home`, `robot.stop` y `arm.greet`
provisional, la política local, el contexto presente, la conversación textual,
los proveedores concretos y la traducción a contratos de Cortex. También posee
el adaptador robótico simulado porque demuestra la composición del sistema
completo, no una responsabilidad nueva del núcleo determinista.

También pertenecen a SIRAH los futuros puertos internos de cámara, voz, LLM y
memoria, sus adaptadores concretos, la persistencia SQLite, MQTT o Serial, y la
composición mediante CLI, GUI o daemon. No se crean todavía porque no existe
código real que los justifique.

Cortex no importa código de SIRAH. SIRAH depende de la distribución
`sirah-cortex==0.1.0a1` y usa preferentemente su fachada pública. `arm.greet`
reutiliza provisionalmente planificación desde submódulos de Cortex y puede
cambiar durante la serie alpha.

## Código heredado

El [prototipo anterior](https://gitlab.com/Laxxup/ipt-sirah) es una fuente de
experiencia y conocimiento histórico. Ninguno de sus componentes se migra
automáticamente al SIRAH actual.

Cada recuperación debe identificar la responsabilidad, comprobar procedencia y
licencia, revisar dependencias y pruebas, ubicar el componente en la frontera
actual y validarlo de forma aislada. La existencia de Gemini, Vosk, Piper,
SQLite, cámaras, reconocimiento facial, MQTT, ESP32-CAM, GTK o LibAdwaita en el
prototipo no demuestra que esas capacidades estén implementadas o sean estables
en este repositorio.

## Firmware

Posee canales PCA9685, ángulos, pulsos, límites locales, GPIO, I2C,
calibraciones, alimentación y comportamiento del microcontrolador.

El flujo permitido comienza con una propuesta de capacidad en SIRAH. El
catálogo y la política la autorizan; una traducción determinista crea
estructuras de Cortex; `SafetySupervisor` valida; `ActionExecutor` entrega por
`RobotPort`; un adaptador futuro traducirá al firmware.

Un LLM nunca controla directamente GPIO, PWM, PCA9685 ni servos.

## Percepción, WorldState e iniciativa

La percepción simulada de SIRAH solo publica eventos estructurados de Cortex.
`Runtime` y el reducer público de Cortex actualizan `WorldState`; SIRAH nunca
lo muta ni mantiene una segunda copia. Las observaciones vencen según los
tiempos definidos por Cortex.

La memoria de interacción de SIRAH conserva únicamente conceptos de producto:
presencias ya saludadas, cooldown, modo silencio, autonomía, iniciativa y TTS.
La política de iniciativa es determinista y consulta el `WorldState` de Cortex.
Gemini no decide reglas obvias de saludo.

## Voz simulada

`SpeechPort` y `FakeSpeechOutput` pertenecen a SIRAH. TTS no es movimiento
mecánico y no se fuerza dentro de `RobotPort`. El fake registra texto, permite
cancelación y no usa subprocess, audio, threads ni red. Piper y TTS real están
fuera de alcance.

## Funcionamiento degradado

Sin cámara, micrófono, altavoz, memoria persistente o cuerpo físico, SIRAH
declara el componente como no configurado y continúa por texto con el robot
simulado. No inventa observaciones de sensores ausentes. Sin Gemini utiliza el
fake; un fallo de inteligencia produce cero movimiento.

## Consola de laboratorio y futuro panel local

La SIRAH Laboratory Console consume `ConversationOrchestrator` y
`SystemSnapshot`. Puede presentar conversación, componentes, capacidades,
eventos y resultados, pero no contiene políticas, no llama directamente a
`RobotPort`, no accede al SDK de Gemini y no mantiene estado autoritativo.

Un panel local futuro deberá consumir los mismos servicios públicos y solicitar
acciones mediante `CapabilityPolicy` y Cortex. No se implementan todavía
FastAPI, Flask, WebSocket, HTML, JavaScript, GTK ni Qt.
### Memoria social e iniciativa

`WorldState` de Cortex conserva presencia y expiración genéricas. SIRAH conserva
por separado `presence_key` efímeras, saludos pendientes y confirmados, con TTL
de 600 segundos y máximo de 128 entradas. Una clave de simulación como
`person:one` no es identidad humana.

`PresentSystem` es una proyección de lectura de `InteractionMemory`. El saludo
hablado (`interaction.greet`) no requiere `arm.greet`, que representa un gesto
mecánico opcional. Piper y Vosk siguen planificados; no forman parte de esta
integración.

La memoria valida TTL y capacidad positivos, y el cooldown no puede ser
negativo. La poda se persiste antes de evaluar iniciativas. Una reproducción
activa se representa mediante una única operación `PendingSpeech` asociada a
`presence_key`; finalizar sin operación no confirma ninguna presencia. Los
eventos simulados usan identificadores deterministas con secuencia, fuente y
clave operacional.
