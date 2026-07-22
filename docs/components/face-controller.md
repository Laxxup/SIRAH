# Controlador facial

- Estado: Planeado
- Validación: No validado
- Bloqueado: faltan firmware, calibraciones y evidencia de pruebas físicas

## Propósito y alcance

Controlar movimientos faciales concretos sin trasladar detalles mecánicos a
Cortex. El equipo identifica un ESP32, un PCA9685 y siete servos.

## Entradas, salidas e interfaces

La entrada futura será un protocolo de capacidades todavía no definido. Las
salidas serán señales PCA9685 hacia servos. No existe adaptador ni contrato de
transporte comprobado.

## Mapa conocido

| Canal | Función |
|---|---|
| 0 | vista horizontal |
| 1 | vista vertical |
| 2 | párpado inferior derecho |
| 3 | párpado superior derecho |
| 4 | párpado inferior izquierdo |
| 5 | párpado superior izquierdo |
| 8 | boca |

## Hardware, software y dependencias

Hardware declarado: ESP32, PCA9685 y siete servos. No se encontró firmware del
controlador, librería elegida, diagrama eléctrico, fuente de alimentación ni
calibraciones. El saludo Velxio existente usa un único servo y no valida este
controlador.

## Seguridad y pruebas

Antes de implementar deben definirse alimentación separada, tierra común,
límites mecánicos, posición segura, parada, rangos PWM y procedimiento manual.
No hay pruebas de simulación ni hardware del conjunto facial.

## Próximos pasos

Recuperar el firmware real si existe, documentar cableado y alimentación,
validar cada canal individualmente y solo después definir el protocolo y el
adaptador de SIRAH.

