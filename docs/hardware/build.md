# Montaje de hardware

Este repositorio controla el subsistema ocular de SIRAH: un ESP32, un PCA9685
y seis servos. Consulta `pin-map.md` antes de cambiar cableado o calibración.

## Alimentación y cableado

- Conecta el PCA9685 en la dirección I2C `0x40` usando los pines declarados en
  `firmware/sirah-eyes/platform/pins.h`.
- Conecta los seis servos únicamente a los canales de `config/actuators.yaml`.
- Alimenta los servos desde un rail externo regulado de 5 V dimensionado para
  su carga de bloqueo.
- Une el GND de la fuente externa, el del PCA9685 y el del ESP32.
- No alimentes el rail de servos desde la conexión USB del ESP32. Un brownout
  puede reiniciar el controlador con un servo bajo carga.

## Ejecución

El dispositivo serie debe ser `/dev/ttyUSB*` o `/dev/sirah-eyes`. Arranca
desarmado y luego usa `sirah-runtime --eyes`. Detén y retira la alimentación
de servos antes de cambiar cableado.