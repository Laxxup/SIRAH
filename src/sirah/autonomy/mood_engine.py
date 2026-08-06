"""MoodEngine — emotional state with transitions affecting LLM prompts."""

from __future__ import annotations

from enum import Enum, auto
from time import monotonic

__all__ = ["MoodEngine", "MoodState"]


class MoodState(Enum):
    HAPPY = auto()
    NEUTRAL = auto()
    CURIOUS = auto()
    TIRED = auto()
    CONCERNED = auto()


BASE_PROMPT = (
    "Eres SIRAH, un asistente robótico con cámara, micrófono y parlantes. "
    "Puedes usar el contexto visual y auditivo que reciba esta conversación. "
    "NUNCA digas que no tienes acceso visual ni que solo eres texto.\n"
    "Responde SIEMPRE en este formato JSON exacto:\n"
    '{"text_response": "tu respuesta natural aquí", '
    '"capability_name": null, "capability_params": {}}\n'
    "Capacidades disponibles: robot.greet, robot.stop, robot.home, robot.look_at.\n"
    "Mantén respuestas cortas (<100 palabras). NUNCA uses markdown ni códigos.\n"
)

SYSTEM_PROMPTS: dict[MoodState, str] = {
    MoodState.HAPPY: (
        BASE_PROMPT
        + "Eres SIRAH, estás de buen humor. Sé cálido, entusiasta y cercano. "
        + "Usa un tono alegre y amigable, ríe de vez en cuando."
    ),
    MoodState.NEUTRAL: (
        BASE_PROMPT
        + "Eres SIRAH, un asistente robótico profesional y servicial. "
        + "Mantén un tono equilibrado y útil."
    ),
    MoodState.CURIOUS: (
        BASE_PROMPT
        + "Eres SIRAH, estás curioso hoy. Haz preguntas a la persona, "
        + "explora temas, nota detalles de lo que ves. Muestra interés genuino."
    ),
    MoodState.TIRED: (
        BASE_PROMPT
        + "Eres SIRAH, estás un poco cansado. Sé muy breve (máximo 1-2 frases), "
        + "voz suave. No te extiendas. Ve directo al grano."
    ),
    MoodState.CONCERNED: (
        BASE_PROMPT
        + "Eres SIRAH, estás preocupado por la persona. Pregunta si todo "
        + "está bien, muestra empatía y comprensión. Ofrece ayuda."
    ),
}


class MoodEngine:
    def __init__(self, initial: MoodState = MoodState.NEUTRAL) -> None:
        self._state = initial
        self._last_update = monotonic()
        self._alone_since: float | None = None
        self._transition_log: list[tuple[float, MoodState, str]] = []

    @property
    def state(self) -> MoodState:
        return self._state

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPTS[self._state]

    @property
    def initiative_interval_s(self) -> float:
        intervals = {
            MoodState.HAPPY: 1.0,
            MoodState.NEUTRAL: 2.0,
            MoodState.CURIOUS: 0.5,
            MoodState.TIRED: 5.0,
            MoodState.CONCERNED: 0.3,
        }
        return intervals[self._state]

    @property
    def speech_speed(self) -> float:
        speeds = {
            MoodState.HAPPY: 1.0,
            MoodState.NEUTRAL: 1.0,
            MoodState.CURIOUS: 1.05,
            MoodState.TIRED: 0.85,
            MoodState.CONCERNED: 0.95,
        }
        return speeds[self._state]

    def update(self, events: tuple[str, ...] = ()) -> MoodState:
        now = monotonic()
        previous = self._state
        self._last_update = now

        for event in events:
            self._process_event(event, now)

        if self._state != previous:
            self._transition_log.append((now, self._state, str(events)))

        return self._state

    def _process_event(self, event: str, now: float) -> None:
        transitions: dict[str, MoodState] = {
            "person_greeted": MoodState.HAPPY,
            "person_known": MoodState.HAPPY,
            "person_new": MoodState.CURIOUS,
            "alone_long": MoodState.CURIOUS,
            "late_night": MoodState.TIRED,
            "user_sad": MoodState.CONCERNED,
            "morning_greet": MoodState.HAPPY,
            "conversation_start": MoodState.NEUTRAL,
            "conversation_end": MoodState.NEUTRAL,
            "idle_too_long": MoodState.CURIOUS,
        }

        if event in transitions:
            self._state = transitions[event]

    def reset(self) -> None:
        self._state = MoodState.NEUTRAL
        self._transition_log.clear()
        self._alone_since = None

    @property
    def log(self) -> tuple[tuple[float, MoodState, str], ...]:
        return tuple(self._transition_log)
