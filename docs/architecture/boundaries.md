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
