# Roadmap de reconstrucción

## Hito completado

SIRAH Cortex `0.1.0a1` establece una primera distribución alpha local del
núcleo determinista. Este hito aporta contratos, estado, Runtime, planificación,
seguridad, ejecución y tracking comprobados, sin afirmar estabilidad definitiva
ni certificación para hardware real.

## Trabajo activo

El único artefacto ejecutable recuperado es el saludo Velxio experimental con
un servo. Debe conservar su carácter de demostración y no convertirse en el
protocolo definitivo.

La separación de repositorios asigna a SIRAH conversación, percepción,
proveedores, dispositivos, adaptadores concretos, firmware, experimentos y
composición. Los marcadores vacíos de Cortex no se copiaron: cada estructura se
creará solo al existir una implementación comprobable.

## Fases siguientes

| Orden | Fase | Resultado esperado |
|---|---|---|
| 1 | Integración simulada SIRAH–Cortex | Un caso de uso mínimo usa la distribución de Cortex sin hardware y conserva sus compuertas de seguridad |
| 2 | Un servo real | Movimiento limitado, alimentado y detenido de forma segura, con evidencia en hardware |
| 3 | Gemini por texto | Entrada y salida textual sin autoridad mecánica directa |
| 4 | Contexto de sesión | Estado conversacional acotado y separado de `WorldState` |
| 5 | Voz | Experimento medible de entrada y salida de audio |
| 6 | Visión | Adquisición y observación reproducibles antes de reconocimiento persistente |
| 7 | Integración multimodal | Coordinación comprobable de texto, voz, visión y capacidades robóticas |
| 8 | Robustecimiento | Manejo de fallos, seguridad, privacidad, observabilidad y validación prolongada |

Antes del servo real deben documentarse alimentación, cableado, límites,
calibraciones y parada física. Antes de visión debe inventariarse la ESP32-CAM
real. Cada fase debe demostrar un consumidor concreto antes de crear paquetes,
puertos o adaptadores.

La promoción desde `experiments/` exige objetivo, procedimiento, resultado,
decisión y evidencia de simulación o hardware.
