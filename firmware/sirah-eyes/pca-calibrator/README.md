# Calibrador PCA9685 de SIRAH

Este sketch es una herramienta propia de SIRAH para medir los ángulos de sus
seis servos oculares. No es el firmware normal del robot. Inicia desarmado y
apaga los seis canales hasta recibir `ARM`.

## Antes de mover un servo

Si un ojo se traba, vibra, deriva o se mueve en una dirección inesperada, no
amplíes un límite de software primero. Revisa el tornillo del horn, varillaje,
topes mecánicos, servo correcto, canal PCA, cableado, fuente externa y GND
común. Recalibra solo después de corregir la causa mecánica o eléctrica.

## Requisitos y conexiones

- ESP32 clásico.
- PCA9685 con dirección I2C `0x40`.
- GPIO21 del ESP32 a SDA y GPIO22 a SCL.
- Fuente externa regulada de 4.8-6.4 V para el rail de servos.
- GND común entre ESP32, PCA9685 y fuente externa.
- CH0 ojo X, CH1 ojo Y, CH2 párpado superior derecho, CH3 inferior derecho,
  CH4 superior izquierdo y CH5 inferior izquierdo.

No alimentes seis servos desde el pin de 5 V del ESP32.

## Cargar el sketch

Con Arduino CLI:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/sirah-eyes/pca-calibrator
arduino-cli upload -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32 firmware/sirah-eyes/pca-calibrator
arduino-cli monitor -p /dev/ttyUSB0 -c baudrate=115200
```

Con Arduino IDE, instala la plataforma ESP32 y la biblioteca `Adafruit PWM
Servo Driver`, abre `pca-calibrator.ino`, elige tu placa ESP32 y el puerto,
sube el sketch y abre Serial Monitor a 115200 baudios con final de línea nuevo.

## Sesión de calibración

`SET` mueve un solo canal entre 0 y 180 grados. `SAVE <etiqueta>` guarda el
ángulo actual solo si corresponde al canal que acabas de mover.

```text
ARM
SET X 110
SAVE EYE_X_CENTER
SET SD 80
SAVE SUP_RIGHT_CLOSED
SHOW
DISARM
```

Formas aceptadas para mover: `SET X 110`, `SET SD 80`, `SET 2 80`, o las formas
cortas heredadas `X110`, `SD80`, `ID69`, `SI87`, `II130`.

Completa estas etiquetas antes de exportar:

```text
EYE_X_LEFT EYE_X_CENTER EYE_X_RIGHT
EYE_Y_UP EYE_Y_CENTER EYE_Y_DOWN
SUP_RIGHT_OPEN SUP_RIGHT_CLOSED
INF_RIGHT_OPEN INF_RIGHT_CLOSED
SUP_LEFT_OPEN SUP_LEFT_CLOSED
INF_LEFT_OPEN INF_LEFT_CLOSED
```

Comandos:

| Comando | Efecto |
|---|---|
| `ARM` | Habilita movimientos. |
| `DISARM` | Apaga PWM de todos los canales. |
| `SET <canal> <ángulo>` | Mueve el canal 0-5. |
| `SET X|Y|SD|ID|SI|II <ángulo>` | Mueve un actuador por nombre. |
| `SAVE <etiqueta>` | Captura el ángulo del canal seleccionado. |
| `SHOW` | Muestra canales, etiquetas y valores pendientes. |
| `SAVE` | Guarda el perfil temporal en NVS del ESP32. |
| `LOAD` | Recupera ese perfil temporal. |
| `EXPORT` | Imprime bloques para `calibration.h` y `actuators.yaml`. |
| `CENTER` | Recupera posiciones iniciales del calibrador sin mover servos. |

`SAVE` y `LOAD` sirven para sobrevivir a un reinicio durante la sesión. NVS no
es la calibración oficial: puede perderse o pertenecer a otra tarjeta.

## Aplicar el resultado oficial

Tras completar las catorce etiquetas, ejecuta `EXPORT`, copia el bloque de C++
a `firmware/sirah-eyes/config/calibration.h` y el bloque YAML a
`config/actuators.yaml`. Conserva ambos valores idénticos y verifica:

```bash
uv run sirah-calibrate validate
make -C firmware/sirah-eyes/tests/host core_tests
```

Finalmente versiona la medición en Git junto con una nota de fecha y la
evidencia física en `docs/hardware/pin-map.md`.
