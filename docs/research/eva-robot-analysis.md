# Research: EVA Robot

**Repositorio:** [Laura-VFA/Affective-Proactive-EVA-Robot](https://github.com/Laura-VFA/Affective-Proactive-EVA-Robot)
**Fecha de análisis:** 2026-08-05
**Relevancia para SIRAH:** ALTA (autonomía + proactividad)

## Resumen

EVA es un robot social, afectivo y proactivo para adultos mayores. Corre en Raspberry Pi 4B
con cámara Intel RealSense D435i, matriz de micrófonos Matrix Voice, pantalla AMOLED y parlantes.

## Lecciones clave

### 1. Wakeface (activación por mirada)

EVA no usa "wake word". Se activa cuando detecta que una persona la está mirando.
Esto es más natural que un comando de voz para robots sociales.

**Aplicación en SIRAH:** Podemos implementar "wakeface" usando MediaPipe FaceDetection.
Si una persona mira directamente a la cámara (bbox centrado + ojos detectables),
SIRAH inicia conversación automáticamente.

### 2. Preguntas proactivas

EVA tiene un archivo `proactive_phrases.json` con frases en español que usa para
iniciar conversación. Las preguntas no son aleatorias — dependen del contexto
(hora del día, persona detectada, historial).

Ejemplos:
- "¿Cómo estás?"
- "¿Quién eres?"
- "¿Necesitas algo?"
- "Hace calor hoy, ¿no?"

**Aplicación en SIRAH:** `autonomy/proactive_topics.py` con frases contextuales
+ capacidad del LLM (Groq) para generar temas nuevos.

### 3. Telegram autónomo

EVA puede enviar y recibir mensajes de Telegram sin intervención humana.
Si detecta algo relevante (persona nueva, estado anómalo), notifica al dueño.

**Aplicación en SIRAH:** Futuro — notificaciones cuando SIRAH detecta eventos relevantes.

### 4. Diseño afectivo

EVA muestra emociones en pantalla (ojos animados) y adapta su comportamiento.
El tono de voz y las respuestas cambian según el contexto emocional.

**Aplicación en SIRAH:** `autonomy/mood_engine.py` — modifica el prompt del LLM
según estado emocional (feliz, neutro, curioso, cansado, preocupado).

## Arquitectura de EVA

```
main.py
├── services/
│   ├── camera_service.py       (RealSense)
│   ├── stt_service.py          (Google STT)
│   ├── tts_service.py          (Google TTS)
│   ├── translator_service.py   (Google Translate)
│   ├── telegram_service.py     (Telethon)
│   └── watson_service.py       (IBM Watson Assistant)
├── files/
│   ├── proactive_phrases.json  (Frases proactivas en español)
│   └── faces/                  (Rostros conocidos)
└── credentials/                (API keys externas)
```

## Lo que SIRAH ya hace mejor

- LLM local/cloud (Groq) en vez de IBM Watson (más flexible)
- Piper TTS local (sin depender de Google Cloud)
- Arquitectura asíncrona (EVA es síncrona)
- Tipos tipados + tests (EVA no tiene tests)
- Capa bridge para distribución laptop↔Pi 4B

## Lo que SIRAH debería adoptar

1. **Wakeface** — activación por detección de mirada directa
2. **Frases proactivas contextuales** — `proactive_topics.py`
3. **Memoria de personas** — `person_tracker.py` con embeddings faciales
4. **Telegram notifications** — fase futura
5. **Pantalla de expresión** — fase hardware (OLED/AMOLED en Pi 4B)
