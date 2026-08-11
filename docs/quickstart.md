# SIRAH v0.3.0 — Quickstart

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana** (only in
Spanish, never translated). Two paths: **no hardware** (FakeESP32 twin,
under 3 minutes) and **real hardware** (under 5 minutes on top).

Prerequisitos: Python ≥ 3.12 en PC o Raspberry Pi 4.

## 1. Sin hardware — FakeESP32 (recomendado primero)

```bash
git clone <url-del-repo> sirah
cd sirah
python -m venv .venv && source .venv/bin/activate
pip install -e ".[cli,serial]"
sirah-runtime --fake --eyes
```

Qué debe pasar: el runtime arma los ojos sobre el gemelo FakeESP32,
registra `eyes: READY`, mantiene el heartbeat y Ctrl-C lo detiene
limpiamente. Los componentes que fallan **degradan** en vez de matar la
app (compruébalo desarmando un componente).

Opciones útiles: `--verbose` para ver el registro de estados, `--fake`
selecciona el twin (ADR-0010), `SIRAH_EYES=0` desarma los ojos.

## 2. Con hardware real

Material (ver [docs/hardware/pin-map.md](hardware/pin-map.md), ADR-0011):

- ESP32 + PCA9685 (0x40) + rail de 6 servos + fuente externa 5 V con GND
  común (el ESP32 se alimenta por USB solo para lógica/flasheo).
- Cable USB-UART al dispositivo `/dev/ttyUSB0` (allowlist ADR-0002).

Instala la regla udev para un nombre estable `/dev/sirah-eyes` (opcional;
por defecto se usa `/dev/ttyUSB0`):

```bash
# udev rule: SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="sirah-eyes"
```

Flasha el firmware (`platform/main.ino`, Arduino IDE o plataforma CLI) y
arranca:

```bash
sirah-runtime --eyes
sirah-runtime --eyes --device /dev/sirah-eyes   # o el nombre del puerto
```

## 3. Validar la calibración

```bash
sirah-calibrate validate
```

Comprueba que `config/actuators.yaml` espeja sin divergencias
`firmware/sirah-eyes/config/calibration.h` y `platform/pins.h` (ADR-0009).

## 4. Problemas frecuentes

| Síntoma | Causa probable | Fix |
|---|---|---|
| `device '...' not allowlisted` | El dispositivo no matchea la allowlist | Usar `/dev/ttyUSB*` o `/dev/sirah-eyes` |
| Falta PyYAML al cargar config | Extra `[cli]` no instalado | `pip install -e ".[cli,serial]"` |
| `eyes: DEGRADED` al bootear | Serial ocupada o ESP32 sin flash | Cerrar otros programas, verificar cable |
| Servos no responden | Falta la fuente 5 V / brownout | Fuente externa + GND común (ADR-0011) |

## 5. Prototipo conversacional experimental

El prototipo conversacional no controla los ojos ni requiere el ESP32. Consulta
[conversation.md](conversation.md) para ejecutar el replay offline y conocer
los requisitos de microfono, Ollama y TTS.
