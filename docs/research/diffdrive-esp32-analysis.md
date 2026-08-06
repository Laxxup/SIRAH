# Research: diffdrive_esp32

**Repositorio:** [Sreerajvr172001/diffdrive_esp32](https://github.com/Sreerajvr172001/diffdrive_esp32)
**Fecha de análisis:** 2026-08-05
**Relevancia para SIRAH:** MEDIA (fase 3 — movilidad con ruedas)

## Resumen

Plugin `ros2_control` para robot diferencial de 2 ruedas con ESP32.
Raspberry Pi 4 ejecuta ROS 2 Humble, ESP32 controla motores y encoders
vía UART serial. Producción-ready, bien documentado, 11 estrellas.

## Lecciones clave

### 1. Protocolo serial limpio

El ESP32 recibe comandos simples por UART a 115200 baud:

```
Comando  Significado
m L R    Mover motores (ticks/sec)
e        Leer encoders
l P I D  Set PID izquierdo
n P I D  Set PID derecho
```

**Aplicación en SIRAH:** Nuestro protocolo `hardware/esp32/README.md` ya define
comandos JSON (`{"cmd": "servo", "id": 0, "angle": 90}`). Para motores,
extender con `{"cmd": "move", "left": 100, "right": 100}`.

### 2. PID en el ESP32

El control PID corre en el ESP32, no en la Raspberry Pi. Esto reduce
latencia y libera CPU en el cerebro principal.

**Aplicación en SIRAH:** Toda la lógica de control de bajo nivel (PID de motores,
interpolación de servos) debe correr en los ESP32. SIRAH solo envía comandos
de alto nivel ("gira 45°", "mueve brazo a posición X").

### 3. Hardware Abstraction con ros2_control

```cpp
class DiffBotSystem : public hardware_interface::SystemInterface {
    // read()  — lee encoders del ESP32 → estado
    // write() — envía velocidades al ESP32
};
```

**Aplicación en SIRAH:** `ActionRunner` ya abstrae los comandos al robot.
Cuando integremos ROS 2, `ActionRunner` publicará en topics en vez de
llamar directamente al simulated robot.

### 4. Configuración externalizada

Parámetros en YAML/XML, no hardcodeados:

```yaml
wheel_separation: 0.10
wheel_radius: 0.0325
update_rate: 50
```

**Aplicación en SIRAH:** Ya usamos `build_system()` con parámetros explícitos.
Para hardware físico, añadir archivo de configuración YAML/TOML.

## Lo que SIRAH no necesita (por ahora)

- `ros2_control` plugin (no usamos ROS 2 aún)
- SLAM/navegación (somos estacionarios)
- Odometría (sin ruedas)

## Lo que SIRAH adoptará en fases futuras

1. **Protocolo serial JSON extendido** para motores
2. **PID en ESP32** para control de velocidad
3. **Configuración externa YAML** para hardware físico
4. **ros2_control bridge** cuando migremos a ROS 2
