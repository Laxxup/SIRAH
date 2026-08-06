# ADR-009: Mood Engine for Emotional State

**Estado:** Accepted
**Fecha:** 2026-08-05
**Autores:** SIRAH v2 development

## Contexto

Un robot social debe tener personalidad. Sin estado emocional, SIRAH siempre
responde igual sin importar el contexto. Un MoodEngine permite:

- Respuestas más cálidas o más formales según el momento
- Variación en frecuencia de iniciativa
- Adaptación al estado del usuario (detecta tristeza → tono preocupado)
- Sensación de "estar vivo" para el usuario

Opciones evaluadas:
1. Sin estado (actual) — respuestas neutras siempre
2. MoodEngine determinista — estados con reglas fijas
3. MoodEngine basado en LLM — el LLM decide el estado
4. MoodEngine híbrido — reglas + LLM para fine-tuning

## Decisión

Implementar un **MoodEngine determinista** con 5 estados y transiciones basadas
en reglas. El estado modifica el prompt del LLM (system prompt dinámico).

### Estados

```
HAPPY ↔ NEUTRAL ↔ CURIOUS ↔ TIRED ↔ CONCERNED
```

### Transiciones

| Evento | Transición |
|--------|-----------|
| Ver persona conocida | NEUTRAL/TIRED → HAPPY |
| Mucho tiempo solo (>30min) | HAPPY → CURIOUS |
| Hora tardía (>22:00) | ANY → TIRED |
| Expresión triste detectada | ANY → CONCERNED |
| Conversación activa | CURIOUS → NEUTRAL |
| Saludo matutino | TIRED → HAPPY |

### Impacto en el LLM

Cada estado modifica el system prompt:

```
HAPPY:     "Eres SIRAH, estás contento/a. Sé cálido, usa emojis."
NEUTRAL:   "Eres SIRAH. Sé profesional y servicial."
CURIOUS:   "Eres SIRAH, estás curioso/a. Haz preguntas, explora temas."
TIRED:     "Eres SIRAH, estás cansado/a. Sé breve, voz suave."
CONCERNED: "Eres SIRAH, estás preocupado/a. Pregunta si todo está bien."
```

### Implementación

```python
class MoodEngine:
    def update(self, events: tuple[str, ...]) -> MoodState
    def system_prompt_override(self) -> str
    def initiative_frequency(self) -> float  # segundos entre checks
    def speech_speed(self) -> float           # 0.8-1.2 multiplier
```

### Consecuencias

- **Positivo:** Personalidad visible para el usuario
- **Positivo:** Determinista y testeable (sin depender del LLM para el estado)
- **Positivo:** Impacto real en las respuestas vía prompt dinámico
- **Negativo:** 5 estados pueden ser pocos — expandir a futuro
- **Negativo:** Las transiciones son reglas fijas — no aprende del usuario

## Referencias

- EVA Robot affective computing: `docs/research/eva-robot-analysis.md`
- InMoov ROS2 reactive behaviors: `docs/research/inmoov-ros2-analysis.md`
