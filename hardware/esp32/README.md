# ESP32 Firmware

Coloca aquí tus sketches de Arduino (.ino) para el control de servos.

## Estructura sugerida

```
hardware/esp32/
├── README.md              Este archivo
├── servo_controller/      Controlador PCA9685 para servos faciales
│   └── servo_controller.ino
├── serial_protocol/       Protocolo JSON de comunicación serie
│   └── serial_protocol.ino
├── body_controller/       Controlador de cuerpo (brazos, cuello)
│   └── body_controller.ino
└── config/                Configuraciones de pines y calibración
    └── pinout.h
```

## Protocolo serie

La laptop envía comandos JSON por Serial a 115200 baud:

```json
{"cmd": "servo", "id": 0, "angle": 90}
{"cmd": "servo", "id": 1, "angle": 45}
{"cmd": "servo_group", "ids": [0,1,2], "angles": [90,45,0]}
{"cmd": "home"}
{"cmd": "ping"}
```

El ESP32 responde con:

```json
{"status": "ok", "id": 0, "angle": 90}
{"status": "error", "msg": "invalid servo id"}
{"status": "pong"}
```

## Pines por defecto (PCA9685)

| Pin ESP32 | Función |
|-----------|---------|
| GPIO21    | SDA     |
| GPIO22    | SCL     |
| 3.3V      | VCC     |
| GND       | GND     |

## Librerías necesarias

- Adafruit PWM Servo Driver Library
- Wire (incluida)
- ArduinoJson
