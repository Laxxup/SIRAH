# Límites entre SIRAH, Cortex y firmware

## Cortex

Posee comandos y eventos genéricos, `WorldState`, Runtime, planes,
`SafetySupervisor`, `ActionExecutor`, `PlanDispatcher`, `RobotPort`, tracking,
cancelación, emergencia y resultados. No posee canales, ángulos, PWM, GPIO,
calibraciones ni proveedores concretos.

## SIRAH

Poseerá el catálogo de capacidades (`face.look`, `face.blink`,
`face.speech.start`, `vision.capture`, `dialogue.listen`), conversación,
percepción, clientes concretos, protocolos y traducción a contratos de Cortex.
Estas capacidades son ejemplos de límite, no afirmaciones de implementación.

## Firmware

Posee canales PCA9685, ángulos, pulsos, límites locales, GPIO, I2C,
calibraciones, alimentación y comportamiento del microcontrolador.

Flujo permitido:

```text
SIRAH solicita capacidad → Cortex planifica y valida → RobotPort despacha
→ adaptador traduce → firmware ejecuta
```

Un LLM nunca controla directamente GPIO, PWM, PCA9685 ni servos.

