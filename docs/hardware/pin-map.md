# Pin map — SIRAH eyes

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana**; this
document covers the eyes subsystem of the general SIRAH project.

**Status: VERIFIED — PCA9685 (ADR-0011), physical evidence 2026-08-09.**

Servos ride on a PCA9685 (addr 0x40) driven over I2C from the ESP32
(SDA GPIO21, SCL GPIO22). Servo rail powered by an external 4.8–6.4 V
supply (4xAA NiMH/alkaline) with common GND; the ESP32 stays on USB power
for logic/flashing only (brownout evidence 2026-08-09).

| Actuator | PCA9685 channel |
|---|---|
| Ojo X | 0 |
| Ojo Y | 1 |
| Párpado superior derecho | 2 |
| Párpado inferior derecho | 3 |
| Párpado superior izquierdo | 4 |
| Párpado inferior izquierdo | 5 |

## Evidence log (verified 2026-08-09, director + executor on hardware)

Calibration firmware with sweep mode (`SWX`/`SWY` commands) drove each
actuator while the director observed the mechanism. All six actuators
responded on the channels above; no wrong-channel findings.

| Channel | Actuator | Sweep result (2026-08-09) | Verdict |
|---|---|---|---|
| 0 | Ojo X | izquierda 150, centro 110, derecha 50 | MEDIDO 2026-08-12 |
| 1 | Ojo Y | arriba 110, centro 70, abajo 40 | MEDIDO 2026-08-12 |
| 2 | Sup der | 157 abierto / 80 cerrado | MEDIDO 2026-08-12 |
| 3 | Inf der | 20 abierto / 69 cerrado | MEDIDO 2026-08-12 |
| 4 | Sup izq | 87 abierto / 150 cerrado | MEDIDO 2026-08-12 |
| 5 | Inf izq | 130 abierto / 70 cerrado | MEDIDO 2026-08-12 |

The corresponding corners live in `firmware/sirah-eyes/config/calibration.h`
(the registered hardware asset). `platform/pins.h` holds the channel map
above. If any future correction is measured, it lands in BOTH this document
and `config/calibration.h` in the same commit — physical evidence wins (A5).

## Referencia mecánica y licencia

El prototipo ocular toma como referencia conceptual el modelaje 3D de
[@WillCogley](https://github.com/willcogley) para
[EyeMech epsilon 3.2](https://www.youtube.com/watch?v=bAvuMn8QTo4&t=186s).
EyeMech está disponible bajo
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

SIRAH usa una electrónica y firmware propios: ESP32 + PCA9685 por I2C; EyeMech
usa otro controlador y PWM directo. Los ángulos de EyeMech no se copian ni se
consideran calibración de SIRAH. Cada ensamblaje requiere su propia medición.
SIRAH no incluye ni redistribuye modelos 3D, código, PCB, BOM, archivos de
fabricación, imágenes ni texto de EyeMech dentro de su distribución Apache-2.0.
Si se usan piezas o derivados mecánicos de EyeMech, conserva su atribución y
licencia y consulta a @WillCogley para cualquier uso comercial.

## Calibración guiada

Antes de cambiar un ángulo, inspecciona el tornillo del horn, varillaje, topes
mecánicos, canal PCA, cableado, fuente externa y GND común. Si un ojo se traba,
deriva o se mueve mal, corrige primero la mecánica o alimentación: no amplíes un
límite numérico para forzar el movimiento.

Requisitos: ESP32, PCA9685 en `0x40`, seis servos, GPIO21 (SDA), GPIO22 (SCL),
fuente externa de 4.8-6.4 V para los servos y GND común con el ESP32. Los
canales son CH0 ojo X, CH1 ojo Y, CH2 superior derecho, CH3 inferior derecho,
CH4 superior izquierdo y CH5 inferior izquierdo.

El sketch `firmware/sirah-eyes/pca-calibrator/` es una herramienta propia de
SIRAH. Inicia `DISARMED`; `ARM` permite mover un canal y `DISARM` apaga PWM.
Con Arduino CLI:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/sirah-eyes/pca-calibrator
arduino-cli upload -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32 firmware/sirah-eyes/pca-calibrator
arduino-cli monitor -p /dev/ttyUSB0 -c baudrate=115200
```

En Arduino IDE, instala la plataforma ESP32 y la biblioteca `Adafruit PWM Servo
Driver`, abre `pca-calibrator.ino`, elige la placa ESP32 y el puerto correcto,
sube el sketch y abre Serial Monitor a 115200 baudios con final de línea nuevo.

Ejemplo de sesión:

```text
ARM
SET X 110
SAVE EYE_X_CENTER
SET SD 80
SAVE SUP_RIGHT_CLOSED
SHOW
EXPORT
DISARM
```

Completa las 14 etiquetas: `EYE_X_LEFT`, `EYE_X_CENTER`, `EYE_X_RIGHT`,
`EYE_Y_UP`, `EYE_Y_CENTER`, `EYE_Y_DOWN`, `SUP_RIGHT_OPEN`,
`SUP_RIGHT_CLOSED`, `INF_RIGHT_OPEN`, `INF_RIGHT_CLOSED`, `SUP_LEFT_OPEN`,
`SUP_LEFT_CLOSED`, `INF_LEFT_OPEN` e `INF_LEFT_CLOSED`.
`SAVE <etiqueta>` captura el ángulo actual; `SAVE`/`LOAD` guardan el perfil de
trabajo temporal en NVS y `EXPORT` exige un perfil completo. Copia el resultado
a `calibration.h` y `actuators.yaml`, después ejecuta:

```bash
sirah-calibrate validate
make -C firmware/sirah-eyes/tests/host core_tests
```

La calibración oficial vive en Git; NVS no sustituye los archivos versionados.
Se añadirán fotos propias del ensamblaje en una actualización posterior.

## Behavioral constraints recorded during verification (2026-08-09)

- Eyes must never move while the eyelids are not 100% open (mechanical
  jam risk). The firmware only uses fully open and blink positions.
- A blink needs ~300 ms of sustained closed position to complete physical
  travel before reopening (blink_fsm.h `closed_ms = 300`). No entrecerrado
  pose is defined or used.
- Calibration drifted repeatedly during the session (horn screw loose):
  treat recorded corners as a snapshot, not a constant; re-verify after
  any mechanical intervention.

## Serial device (PC ↔ ESP32)

The ESP32 UART (CP210x/CH340-class) shows up as `ttyUSB*`/`ttyACM*`; the
numbering is not stable across reboots. A udev rule gives the robot a
deterministic name (Stage 5), so the runtime always opens the same path:

```
# /etc/udev/rules.d/99-sirah-eyes.rules
# Replace vendor/product with the real USB-UART bridge:
#   lsusb -> "ID <vid>:<pid>"  ;  udevadm info -a -n /dev/ttyUSB0
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", \
    SYMLINK+="sirah-eyes", MODE="0660", GROUP="dialout"
```

After adding the rule: `sudo udevadm control --reload && sudo udevadm trigger`.
The device then appears at `/dev/sirah-eyes` (set `SIRAH_SERIAL_DEVICE`).
Baud: 115200 8N1 (firmware `main.ino`). Only the runtime opens the port.
