# Roadmap inicial

## Trabajo activo

El único artefacto ejecutable recuperado es el saludo Velxio experimental con
un servo. Debe conservar su carácter de demostración y no convertirse en el
protocolo definitivo.

La separación de repositorios asigna a SIRAH conversación, percepción,
proveedores, dispositivos, adaptadores concretos, firmware, experimentos y
composición. Los marcadores vacíos de Cortex no se copiaron: cada estructura se
creará solo al existir una implementación comprobable.

## Siguientes validaciones

1. Confirmar procedencia y estado del controlador facial real.
2. Documentar alimentación, cableado, límites y calibraciones.
3. Validar los siete canales primero de forma aislada y luego conjunta.
4. Inventariar la ESP32-CAM real antes de elegir transporte.
5. Definir un experimento medible para conversación o percepción.
6. Adoptar el mecanismo SIRAH–Cortex solo al existir un consumidor real.

La promoción desde `experiments/` exige objetivo, procedimiento, resultado,
decisión y evidencia de simulación o hardware.
