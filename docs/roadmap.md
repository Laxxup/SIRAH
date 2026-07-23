# Roadmap de reconstrucción

## Hitos completados

SIRAH Cortex `0.1.0a1` establece una primera distribución alpha local del
núcleo determinista. Este hito aporta contratos, estado, Runtime, planificación,
seguridad, ejecución y tracking comprobados, sin afirmar estabilidad definitiva
ni certificación para hardware real.

SIRAH `0.1.0.dev0` añade una integración pre-alpha simulada con Cortex, contexto
presente en memoria y razonamiento opcional por texto mediante Gemini. La
inteligencia propone capacidades estructuradas; el catálogo, la política local,
Cortex y `RobotPort` conservan la autoridad de ejecución. Las pruebas normales
no usan red.

La SIRAH Laboratory Console y el `SystemSnapshot` completan la demostración
textual de esta pre-alpha. La consola sigue siendo una herramienta de
laboratorio, no un producto final.

## Trabajo activo

El único artefacto ejecutable recuperado es el saludo Velxio experimental con
un servo. Debe conservar su carácter de demostración y no convertirse en el
protocolo definitivo.

La separación de repositorios asigna a SIRAH conversación, percepción,
proveedores, dispositivos, adaptadores concretos, firmware, experimentos y
composición. Los marcadores vacíos de Cortex no se copiaron: cada estructura se
creará solo al existir una implementación comprobable.

## Fases siguientes

| Estado | Fase | Resultado |
|---|---|---|
| Completada | Integración simulada SIRAH–Cortex | `robot.home` y `robot.stop` atraviesan Cortex y un adaptador simulado |
| Completada | Gemini por texto | Decisión estructurada opcional, sin autoridad mecánica directa |
| Completada | Contexto de sesión inicial | Estado reciente acotado, separado de `WorldState` y sin persistencia |
| Siguiente | Un servo real y Serial | Movimiento limitado, alimentado y detenido de forma segura, con evidencia en hardware |
| Planeada | Contexto avanzado | Resumen y políticas de privacidad comprobables |
| Planeada | Voz | Experimento medible de entrada y salida de audio |
| Planeada | Visión | Adquisición y observación reproducibles antes de reconocimiento persistente |
| Planeada | Integración multimodal | Coordinación comprobable de texto, voz, visión y capacidades robóticas |
| Planeada | Robustecimiento | Manejo de fallos, seguridad, privacidad, observabilidad y validación prolongada |

Antes del servo real deben documentarse alimentación, cableado, límites,
calibraciones y parada física. Antes de visión debe inventariarse la ESP32-CAM
real. Cada fase debe demostrar un consumidor concreto antes de crear paquetes,
puertos o adaptadores.

La promoción desde `experiments/` exige objetivo, procedimiento, resultado,
decisión y evidencia de simulación o hardware.
