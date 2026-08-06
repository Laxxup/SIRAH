# Research: InMoov ROS2

**Repositorio:** [aalonsopuig/Inmoov_ROS2](https://github.com/aalonsopuig/Inmoov_ROS2)
**Fecha de análisis:** 2026-08-05
**Relevancia para SIRAH:** ALTA (visión + voz + servos en robot humanoide real)

## Resumen

InMoov ROS2 es un sistema de control completo para el robot humanoide InMoov (Paul).
Usa ROS 2 Jazzy, Arduino para control de servos, visión facial con OpenCV, y
Piper TTS con movimiento de boca sincronizado. Es el proyecto más cercano a
lo que SIRAH aspira ser.

## Lecciones clave

### 1. Arquitectura distribuida

```
Laptop/PC (ROS 2 Master)
├── face_detection_node    (OpenCV + reconocimiento facial)
├── speech_node            (Piper TTS + synced mouth)
├── behavior_node          (Lógica de interacción)
│
Arduino Mega × N (subsystems)
├── Subsystem 1: Cabeza    (6 servos: ojos, cuello, mandíbula)
├── Subsystem 2: Brazo derecho
├── Subsystem 3: Brazo izquierdo
└── PCA9685 × 3            (PWM servo drivers)
```

**Aplicación en SIRAH:** Reemplazar Arduino Mega con ESP32. Cada ESP32 controla
un subsistema (cabeza, brazo derecho, brazo izquierdo) vía Serial/MQTT.

### 2. Reconocimiento facial con embeddings

InMoov usa embeddings faciales para reconocer personas específicas.
No solo detecta "hay una cara", sabe QUIÉN es.

**Aplicación en SIRAH:** `autonomy/person_tracker.py` debe usar MediaPipe
FaceMesh para generar embeddings y comparar con una base de datos local.
Esto permite:
- "Hola [nombre], ¿cómo estás?"
- "Hace 3 días que no te veía"
- Personalidad adaptada por persona

### 3. TTS con boca sincronizada

InMoov usa Piper TTS y sincroniza el movimiento de la mandíbula
con los fonemas generados. Esto hace que el robot se vea más natural.

**Aplicación en SIRAH:** Fase hardware — cuando el ESP32 controle los
servos faciales, usar los timestamps de Piper para mover la mandíbula.

### 4. Comportamientos reactivos

InMoov tiene comportamientos predefinidos que se activan según
lo que la cámara detecta:
- Ve una cara → saluda
- Reconoce a alguien → saludo personalizado
- No ve a nadie → posición de reposo

**Aplicación en SIRAH:** Esto es exactamente lo que queremos con la autonomía.
SIRAH ya tiene `evaluate_initiative()` pero debe extenderse con:
- Reconocimiento de persona específica
- Comportamientos idle (reposo, mirar alrededor)
- Estados emocionales

### 5. Documentación exhaustiva

InMoov ROS2 tiene documentación técnica detallada (7 documentos):
arquitectura, paquetes ROS 2, subsistemas, instalación, uso, licencias.

**Aplicación en SIRAH:** Nuestra carpeta `docs/` debe crecer con:
- ADRs para cada decisión de diseño
- Research notes de proyectos estudiados
- Guías de instalación y uso

## Lo que SIRAH ya hace mejor

- LLM integrado (Groq) vs sin LLM en InMoov
- Arquitectura asíncrona vs ROS 2 síncrono
- Bridge distribuido laptop↔Pi 4B
- Tipos inmutables + tests exhaustivos
- Factory `build_system()` único

## Lo que SIRAH debería adoptar

1. **Reconocimiento facial por embedding** → `person_tracker.py`
2. **Subsistemas por ESP32** → `hardware/esp32/` (ya tenemos carpeta)
3. **Boca sincronizada con TTS** → fase hardware
4. **Comportamientos reactivos + idle** → `autonomy/`
5. **Documentación técnica completa** → `docs/autonomy/` + `docs/research/`
