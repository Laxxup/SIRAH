# Límites entre SIRAH, Cortex y firmware

## Cortex

Posee comandos y eventos genéricos, `WorldState`, Runtime, planes,
`SafetySupervisor`, `ActionExecutor`, `PlanDispatcher`, `RobotPort`, tracking,
cancelación, emergencia y resultados. No posee canales, ángulos, PWM, GPIO,
calibraciones ni proveedores concretos.

## SIRAH

Posee la responsabilidad del catálogo futuro de capacidades (`face.look`, `face.blink`,
`face.speech.start`, `vision.capture`, `dialogue.listen`), conversación,
percepción, clientes concretos, protocolos y traducción a contratos de Cortex.
Estas capacidades son ejemplos de límite, no afirmaciones de implementación.

También pertenecen a SIRAH los futuros puertos internos de cámara, voz, LLM y
memoria, sus adaptadores concretos, la persistencia SQLite, MQTT o Serial, y la
composición mediante CLI, GUI o daemon. No se crean todavía porque no existe
código real que los justifique.

Cortex expone actualmente solo `RobotPort` y `EventInboxPort`; no importa
código de SIRAH. SIRAH podrá depender de Cortex cuando se adopte un mecanismo
técnico de integración.

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

El flujo permitido comienza con una solicitud de capacidad en SIRAH. Cortex la
planifica y valida; `RobotPort` la despacha; un adaptador la traduce y el
firmware la ejecuta.

Un LLM nunca controla directamente GPIO, PWM, PCA9685 ni servos.
