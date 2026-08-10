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
| 0 | Ojo X | moves inside 70–140°, center 110° | VERIFIED |
| 1 | Ojo Y | moves inside 60–85°, center 75° | VERIFIED |
| 2 | Sup der | 110 abierto / 70 cerrado | VERIFIED |
| 3 | Inf der | 10 abierto / 70 cerrado | VERIFIED |
| 4 | Sup izq | 145 abierto / 170 cerrado | VERIFIED |
| 5 | Inf izq | 95 abierto / 40 cerrado | VERIFIED |

The corresponding corners live in `firmware/sirah-eyes/config/calibration.h`
(the registered hardware asset). `platform/pins.h` holds the channel map
above. If any future correction is measured, it lands in BOTH this document
and `config/calibration.h` in the same commit — physical evidence wins (A5).

## Behavioral constraints recorded during verification (2026-08-09)

- Eyes must never move while the eyelids are not 100% open (mechanical
  jam risk). Squint/lowered-lid poses keep the eyes centered and frozen.
- A blink needs ~300 ms of sustained closed position to complete physical
  travel before reopening (blink_fsm.h `closed_ms = 300`).
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