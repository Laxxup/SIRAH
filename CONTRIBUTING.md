# Contribuir a SIRAH

Antes de promover código, documenta propósito, entradas, salidas, seguridad y
evidencia de validación. Usa nombres de código y carpetas en inglés.

Estados permitidos: Planeado, Experimental, En desarrollo, Implementado y
Deprecado. `Bloqueado` es una anotación adicional. La validación se declara
como No validado, Validado en simulación o Validado en hardware.

Los prototipos nacen en `experiments/` con objetivo, procedimiento, resultado y
decisión. Una responsabilidad estable justifica entonces `subsystems/`, un
cliente concreto justifica `adapters/`, y código realmente cargado en un
microcontrolador justifica `firmware/`.

Nunca conectes un LLM directamente con GPIO, PWM, PCA9685 o servos. Toda
capacidad mecánica debe atravesar planificación, seguridad y `RobotPort` de
Cortex antes de que un adaptador la traduzca al firmware.

