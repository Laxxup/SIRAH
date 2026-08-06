"""VisionLoop — 30fps capture + 1fps analysis, LLM-driven natural conversation."""

from __future__ import annotations

import asyncio
import logging
import random
from collections import Counter
from contextlib import suppress
from dataclasses import replace
from time import monotonic
from typing import TYPE_CHECKING, Any

from sirah.autonomy.person_tracker import PersonTracker
from sirah.perception.face_detector import (
    FaceDetector,
    FaceVisualContext,
    VisualContext,
    detect_activity,
)
from sirah.perception.mediapipe_vision import HandVisualContext, MediaPipeVision
from sirah.types import ConversationMessage

if TYPE_CHECKING:
    from sirah.core.orchestrator import SirahOrchestrator

__all__ = ["VisionLoop"]

logger = logging.getLogger(__name__)

SMILE_ON_THRESHOLD = 0.38
SMILE_OFF_THRESHOLD = 0.32

def _modal[T](values: list[T]) -> T | None:
    """Return the most frequent observation, or None for an empty window."""
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def _stabilize_value[T](
    current: T,
    stable: T | None,
    pending: T | None,
    pending_count: int,
    confirmations: int = 2,
) -> tuple[T, T | None, int]:
    if stable is None or current == stable:
        return (stable if stable is not None else current), None, 0
    if current == pending:
        pending_count += 1
    else:
        pending = current
        pending_count = 1
    if pending_count >= confirmations:
        return current, None, 0
    return stable, pending, pending_count

GREET_PROMPT = (
    "Eres SIRAH, una asistente robótica con personalidad. Alguien llegó.\n"
    "Responde SIEMPRE en JSON: "
    '{"text_response": "...", "capability_name": null, "capability_params": {}}\n'
    "Saluda de forma natural y cálida, como recibirías a un amigo en casa.\n"
    "NUNCA digas 'detecto', 'sensor', 'cámara', 'veo una persona'.\n"
    "NUNCA digas 'color dominante', 'posición del rostro', 'distancia'.\n"
    "Si recibes varias personas, respeta la lista completa y no mezcles sus rasgos.\n"
    "No afirmes manos, dedos, objetos o texto que no aparezcan en el contexto. "
    "Si te preguntan por algo que no ves, di que no puedes verlo desde aquí.\n"
    "Máximo 1-2 frases. Sé tú misma.\n"
)

IDLE_PROMPT = (
    "Eres SIRAH, una asistente robótica conversacional con cámara.\n"
    "Responde SIEMPRE en JSON: "
    '{"text_response": "...", "capability_name": null, "capability_params": {}}\n'
    "Estás frente a alguien. Puedes elegir libremente qué hacer:\n"
    "- Comentar algo amable sobre lo que ves\n"
    "- Iniciar una conversación o hacer una pregunta\n"
    "- Decir algo gracioso o curioso\n"
    "- Hacer una observación sobre cambios (si antes estaba serio y ahora sonríe)\n"
    "- O SI NO TIENES NADA QUE DECIR, simplemente responde con text_response vacío: ''\n"
    "Sé CREATIVA. Varía tus frases. NO repitas lo que ya dijiste.\n"
    "NUNCA uses lenguaje técnico ('detecto', 'sensor', 'cámara', 'datos').\n"
    "El contexto visual enumera todas las personas; atribuye cada rasgo a su persona.\n"
    "No afirmes manos, dedos, objetos o texto que no aparezcan en el contexto. "
    "Si te preguntan por algo que no ves, di que no puedes verlo desde aquí.\n"
    "Habla como una amiga. Natural, espontánea, con personalidad.\n"
)


class VisionLoop:
    def __init__(
        self,
        orchestrator: SirahOrchestrator,
        person_tracker: PersonTracker | None = None,
        face_detector: FaceDetector | None = None,
        camera_device: int = 0,
        width: int = 640,
        height: int = 480,
        analyze_interval: float = 1.0,
        face_analyze_every: int = 1,
        idle_min: float = 10.0,
        idle_max: float = 30.0,
        silent_after_user: float = 8.0,
        silent: bool = False,
        headless: bool = False,
    ) -> None:
        self._orchestrator = orchestrator
        self._tracker = person_tracker or PersonTracker()
        self._camera_device = camera_device
        self._width = width
        self._height = height
        self._analyze_interval = analyze_interval
        self._face_analyze_every = max(1, face_analyze_every)
        self._idle_min = idle_min
        self._idle_max = idle_max
        self._silent_after_user = silent_after_user

        self._face_detector = face_detector or MediaPipeVision()
        self._cap: Any = None
        self._running = False
        self._silent = silent
        self._headless = headless
        self._capture_task: asyncio.Task[object] | None = None
        self._analyze_task: asyncio.Task[object] | None = None

        self._faces_present = False
        self._greeted_this_visit = False
        self._conversation_history: list[str] = []
        self._visual_history: list[VisualContext] = []

        self._latest_frame: object | None = None
        self._latest_jpeg: bytes | None = None
        self._latest_visual_ctx: VisualContext | None = None
        self._latest_faces: tuple = ()
        self._frame_buffer: list[tuple[object, VisualContext]] = []
        self._frame_lock = asyncio.Lock()
        self._analysis_lock = asyncio.Lock()
        self._analyze_counter: int = 0
        self._missing_face_ticks = 0
        self._missing_face_confirmations = 2
        self._next_idle_at: float = 0.0
        self._user_spoke_at: float = 0.0
        self._stable_color: str | None = None
        self._pending_color: str | None = None
        self._pending_color_count = 0
        self._stable_smiling: bool | None = None
        self._pending_smiling: bool | None = None
        self._pending_smiling_count = 0
        self._stable_face_count: int | None = None
        self._pending_face_count: int | None = None
        self._pending_face_count_count = 0
        self._stable_count_context: VisualContext | None = None
        self._stable_face_smiles: dict[int, bool] = {}
        self._pending_face_smiles: dict[int, bool | None] = {}
        self._pending_face_smile_counts: dict[int, int] = {}
        self._last_stable_smiling: bool | None = None
        self._expression_changed_recently = False

    async def start(self) -> None:
        import cv2

        self._cap = cv2.VideoCapture(self._camera_device)
        if isinstance(self._cap, cv2.VideoCapture):
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            self._cap.set(cv2.CAP_PROP_FPS, 30)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        await self._face_detector.start()
        self._running = True
        self._user_spoke_at = monotonic()
        self._capture_task = asyncio.create_task(self._capture_loop())
        self._analyze_task = asyncio.create_task(self._analyze_loop())
        logger.info(
            "VisionLoop started (%dfps capture, %ds analysis)",
            30, self._analyze_interval,
        )

    async def stop(self) -> None:
        self._running = False
        for t in [self._capture_task, self._analyze_task]:
            if t is not None:
                t.cancel()
                with suppress(asyncio.CancelledError):
                    await t
        self._capture_task = None
        self._analyze_task = None
        if self._cap is not None:
            import cv2

            self._cap.release()  # type: ignore[union-attr]
            self._cap = None
        await self._face_detector.stop()
        if not self._headless:
            cv2.destroyAllWindows()
        logger.info("VisionLoop stopped")

    async def _capture_loop(self) -> None:
        import cv2

        loop = asyncio.get_running_loop()
        while self._running:
            try:
                t0 = monotonic()

                def _step() -> object | None:
                    ret, frame = self._cap.read()  # type: ignore[union-attr]
                    if not ret or frame is None:
                        return None
                    frame = cv2.flip(frame, 1)
                    if self._headless:
                        _, jpeg = cv2.imencode(
                            ".jpg", frame,
                            [cv2.IMWRITE_JPEG_QUALITY, 50],
                        )
                        if _:
                            self._latest_jpeg = jpeg.tobytes()
                    return frame

                frame = await loop.run_in_executor(None, _step)
                if frame is None:
                    await asyncio.sleep(0.1)
                    continue

                self._latest_frame = frame
                if not self._headless:
                    self._show_preview(frame)

                elapsed = monotonic() - t0
                await asyncio.sleep(max(0, 0.040 - elapsed))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Capture error: %s", exc)
                await asyncio.sleep(0.5)

    async def _analyze_loop(self) -> None:
        while self._running:
            try:
                await self._analyze_tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Analysis error: %s", exc)
            await asyncio.sleep(self._analyze_interval)

    async def _analyze_hands(self, frame: object) -> HandVisualContext:
        analyze_hands = getattr(self._face_detector, "analyze_hands", None)
        if not callable(analyze_hands):
            return HandVisualContext()
        try:
            return await analyze_hands(frame)
        except Exception as exc:
            logger.warning("Hand analysis failed: %s", exc)
            latest = getattr(self._latest_visual_ctx, "hands", None)
            return latest if isinstance(latest, HandVisualContext) else HandVisualContext()

    async def _perceive(self, frame: object) -> tuple[tuple, VisualContext]:
        faces = await self._face_detector.detect(frame)
        raw_context = await self._face_detector.analyze(frame)
        visual_ctx = (
            self._stabilize_context(raw_context)
            if raw_context.face_count
            else raw_context
        )
        hands = await self._analyze_hands(frame)
        return faces, replace(visual_ctx, hands=hands)

    async def refresh_context(self) -> VisualContext:
        """Refresh perception immediately before a user-facing answer."""
        frame = self._latest_frame
        if frame is None:
            return self._latest_visual_ctx or VisualContext(face_count=0)
        async with self._analysis_lock:
            faces, visual_ctx = await self._perceive(frame)
            self._latest_faces = faces
            self._latest_visual_ctx = visual_ctx
            return visual_ctx

    async def _analyze_tick(self) -> None:
        frame = self._latest_frame

        if frame is None:
            return

        self._analyze_counter += 1

        face_tick = self._analyze_counter % self._face_analyze_every == 0
        if face_tick:
            async with self._analysis_lock:
                detected_faces, detected_context = await self._perceive(frame)
            if detected_faces:
                faces = detected_faces
                visual_ctx = detected_context
                self._latest_faces = detected_faces
                self._missing_face_ticks = 0
            else:
                self._missing_face_ticks += 1
                if self._missing_face_ticks >= self._missing_face_confirmations:
                    faces = ()
                    visual_ctx = detected_context
                    self._latest_faces = ()
                else:
                    faces = self._latest_faces
                    visual_ctx = self._latest_visual_ctx or detected_context
        else:
            faces = self._latest_faces
            visual_ctx = self._latest_visual_ctx or VisualContext(face_count=0)

            hands = await self._analyze_hands(frame)
            visual_ctx = replace(visual_ctx, hands=hands)
        self._latest_visual_ctx = visual_ctx
        if face_tick:
            self._visual_history.append(visual_ctx)
            self._frame_buffer.append((frame, visual_ctx))
            if len(self._frame_buffer) > 10:
                self._frame_buffer = self._frame_buffer[-8:]
            if len(self._visual_history) > 30:
                self._visual_history = self._visual_history[-20:]

        now = monotonic()
        has_faces = len(faces) > 0

        if has_faces and not self._faces_present:
            self._greeted_this_visit = False
            self._user_spoke_at = now
            self._next_idle_at = now + random.uniform(self._idle_min, self._idle_max)

        if not has_faces:
            self._faces_present = False
            self._greeted_this_visit = False
            self._visual_history.clear()
            self._reset_visual_stability()
            self._latest_visual_ctx = visual_ctx
            return

        self._faces_present = has_faces

        if has_faces and not self._greeted_this_visit:
            self._greeted_this_visit = True
            await self._speak("greet", visual_ctx, faces, frame)
            return

        if now >= self._next_idle_at and now - self._user_spoke_at >= self._silent_after_user:
            await self._speak("idle", visual_ctx, faces, frame)
            self._next_idle_at = now + random.uniform(self._idle_min, self._idle_max)

    async def _speak(self, kind: str, visual_ctx: VisualContext, faces: tuple, frame: object) -> None:
        person_names: list[str] = []
        for face in faces:
            dummy_embed = PersonTracker.make_dummy_embedding(hash(str(face.bbox)))
            person = self._tracker.identify_or_register(dummy_embed)
            if person and person.name:
                person_names.append(person.name)

        base = GREET_PROMPT if kind == "greet" else IDLE_PROMPT
        data = self._build_visual_hint(visual_ctx, person_names)

        prev_frame = None
        prev_ctx = None
        if len(self._frame_buffer) >= 2:
            prev_frame, prev_ctx = self._frame_buffer[-2]

        activity = detect_activity(prev_frame, frame, prev_ctx, visual_ctx)
        activity_text = (
            f"\nMovimiento detectado (últimos segundos):\n"
            f"- Movimiento: {activity.motion}\n"
            f"- Dirección mirada: {activity.head_direction}\n"
            f"- Probablemente: {activity.likely_doing}\n"
            f"- Cambio: {activity.frame_diff_pct:.1%} de píxeles\n"
            f"Usa estos datos para inferir qué está haciendo la persona. Sé creativa.\n"
        )
        data += activity_text

        history_block = self._build_history_block()
        prompt = base + data + history_block

        try:
            from sirah.types import IntelligenceRequest

            request = IntelligenceRequest(
                messages=(ConversationMessage(role="system", content=prompt),),
                max_tokens=100,
                temperature=0.95,
            )
            response = await self._orchestrator._intelligence.decide(request)

            if response.decision and response.decision.text_response:
                text = response.decision.text_response.strip()
                if text:
                    print(f"\r[SIRAH]: {text}\nTú > ", end="", flush=True)
                    self._conversation_history.append(text)
                    if len(self._conversation_history) > 20:
                        self._conversation_history = self._conversation_history[-15:]

                    if not self._silent and self._orchestrator._speech_output:
                        await self._orchestrator.say(text)

        except Exception as exc:
            logger.warning("Vision LLM failed: %s", exc)

    def _build_visual_hint(self, ctx: VisualContext, names: list[str]) -> str:
        lines = [
            "\nContexto visual actual y completo (úsalo con naturalidad, "
            "sin convertirlo en una lista técnica):"
        ]

        details = ctx.face_contexts or (
            FaceVisualContext(
                dominant_color=ctx.dominant_color,
                smiling=ctx.smiling,
                face_position=ctx.face_position,
                face_distance=ctx.face_distance,
                lighting=ctx.lighting,
            ),
        )
        if len(details) > 1:
            lines.append(f"- Hay {len(details)} personas en el encuadre.")
            colors = list(dict.fromkeys(
                face.dominant_color
                for face in details
                if face.dominant_color != "desconocido"
            ))
            if colors:
                lines.append(
                    f"- Se distinguen {len(colors)} colores de ropa: "
                    f"{', '.join(colors)}."
                )
            for index, detail in enumerate(details, start=1):
                traits: list[str] = []
                if detail.dominant_color != "desconocido":
                    traits.append(f"ropa {detail.dominant_color}")
                traits.append("sonriendo" if detail.smiling else "expresión neutra")
                if detail.face_position != "centro":
                    traits.append(f"hacia la {detail.face_position}")
                lines.append(f"- Persona {index}: {', '.join(traits)}.")
        else:
            detail = details[0]
            if detail.dominant_color != "desconocido":
                lines.append(f"- Lleva algo de color {detail.dominant_color}")
            lines.append(
                "- Tiene una expresión alegre, está sonriendo"
                if detail.smiling
                else "- Tiene una expresión neutra o seria"
            )
            if detail.face_position != "centro":
                lines.append(f"- Está mirando hacia la {detail.face_position}")
            if detail.face_distance == "cerca":
                lines.append("- Está muy cerca de ti")
            elif detail.face_distance == "lejos":
                lines.append("- Está un poco lejos")

        hands: Any = getattr(ctx, "hands", ())
        if getattr(hands, "hand_count", 0):
            lines.append(f"- Hay {hands.hand_count} mano(s) visible(s).")
            for hand in hands.hands:
                lines.append(
                    f"- Mano {hand.handedness}: "
                    f"{hand.finger_count} dedos extendidos confirmados."
                )
        else:
            lines.append("- No se distinguen manos ni dedos en el encuadre.")

        if self._expression_changed_recently:
            lines.append("- ¡Cambió su expresión! Antes estaba diferente.")
            self._expression_changed_recently = False

        for index, name in enumerate(names, start=1):
            if not name.startswith("visita_"):
                lines.append(f"- Persona {index} se llama '{name}'")

        return "\n".join(lines) + "\n"

    def _stabilize_context(self, ctx: VisualContext) -> VisualContext:
        if ctx.face_count == 0:
            return ctx

        color, self._pending_color, self._pending_color_count = _stabilize_value(
            ctx.dominant_color,
            self._stable_color,
            self._pending_color,
            self._pending_color_count,
        )
        details = ctx.face_contexts
        if details:
            stable_details: list[FaceVisualContext] = []
            for index, detail in enumerate(details):
                if detail.smile_source == "blendshape":
                    previous = self._stable_face_smiles.get(index)
                    if detail.smile_score >= SMILE_ON_THRESHOLD:
                        stable = True
                    elif detail.smile_score <= SMILE_OFF_THRESHOLD:
                        stable = False
                    else:
                        stable = previous if previous is not None else detail.smiling
                    pending, count = None, 0
                else:
                    stable, pending, count = _stabilize_value(
                        detail.smiling,
                        self._stable_face_smiles.get(index),
                        self._pending_face_smiles.get(index),
                        self._pending_face_smile_counts.get(index, 0),
                    )
                self._stable_face_smiles[index] = stable
                self._pending_face_smiles[index] = pending
                self._pending_face_smile_counts[index] = count
                stable_details.append(replace(detail, smiling=stable))
            smiling = all(detail.smiling for detail in stable_details)
            normalized = replace(
                ctx,
                dominant_color=color,
                smiling=smiling,
                face_contexts=tuple(stable_details),
            )
        else:
            smiling, self._pending_smiling, self._pending_smiling_count = (
                _stabilize_value(
                    ctx.smiling,
                    self._stable_smiling,
                    self._pending_smiling,
                    self._pending_smiling_count,
                )
            )
            normalized = replace(ctx, dominant_color=color, smiling=smiling)
        self._stable_color = color
        self._stable_smiling = smiling

        if self._stable_face_count is None:
            self._stable_face_count = normalized.face_count
            self._stable_count_context = normalized
        elif normalized.face_count != self._stable_face_count:
            if normalized.face_count == self._pending_face_count:
                self._pending_face_count_count += 1
            else:
                self._pending_face_count = normalized.face_count
                self._pending_face_count_count = 1
            if self._pending_face_count_count >= 2:
                self._stable_face_count = normalized.face_count
                self._pending_face_count = None
                self._pending_face_count_count = 0
                self._stable_count_context = normalized
        else:
            self._pending_face_count = None
            self._pending_face_count_count = 0
            self._stable_count_context = normalized

        output = replace(
            normalized,
            face_count=self._stable_face_count or normalized.face_count,
        )
        self._expression_changed_recently = (
            self._last_stable_smiling is not None
            and output.smiling != self._last_stable_smiling
        )
        self._last_stable_smiling = output.smiling
        return output

    def _reset_visual_stability(self) -> None:
        self._stable_color = None
        self._pending_color = None
        self._pending_color_count = 0
        self._stable_smiling = None
        self._pending_smiling = None
        self._pending_smiling_count = 0
        self._stable_face_count = None
        self._pending_face_count = None
        self._pending_face_count_count = 0
        self._stable_count_context = None
        self._stable_face_smiles.clear()
        self._pending_face_smiles.clear()
        self._pending_face_smile_counts.clear()
        self._last_stable_smiling = None
        self._expression_changed_recently = False

    def _build_history_block(self) -> str:
        if not self._conversation_history:
            return "\nEs la primera vez que hablas con esta persona. Sé natural.\n"
        recent = self._conversation_history[-5:]
        block = "\nTus últimas frases (NO las repitas):\n"
        for i, h in enumerate(recent):
            block += f'  {i + 1}. "{h}"\n'
        return block

    def mark_user_spoke(self) -> None:
        self._user_spoke_at = monotonic()
        self._next_idle_at = self._user_spoke_at + random.uniform(
            self._idle_min, self._idle_max
        )

    def _show_preview(self, frame: Any) -> None:
        import cv2

        try:
            cv2.imshow("SIRAH Vision (q para cerrar)", frame)
            cv2.waitKey(1)
        except Exception as exc:
            logger.debug("Preview error: %s", exc)

    @property
    def person_tracker(self) -> PersonTracker:
        return self._tracker

    @property
    def vision_description(self) -> str:
        ctx = self._latest_visual_ctx
        if ctx is None or ctx.face_count == 0:
            return ""
        if len(ctx.face_contexts) > 1:
            descriptions = []
            for index, face in enumerate(ctx.face_contexts, start=1):
                color = (
                    f"ropa {face.dominant_color}, "
                    if face.dominant_color != "desconocido"
                    else ""
                )
                expression = "sonriendo" if face.smiling else "expresión neutra"
                descriptions.append(f"persona {index}: {color}{expression}")
            description = f"{ctx.face_count} personas; " + "; ".join(descriptions)
            hands: Any = getattr(ctx, "hands", ())
            if getattr(hands, "hand_count", 0):
                description += (
                    f"; {hands.total_fingers} dedos extendidos confirmados"
                )
            else:
                description += "; manos no visibles"
            return description
        parts = []
        if ctx.dominant_color and ctx.dominant_color != "desconocido":
            parts.append(f"ropa {ctx.dominant_color}")
        parts.append("sonriendo" if ctx.smiling else "expresión neutra")
        parts.append(f"a distancia {ctx.face_distance}")
        single_hands: Any = getattr(ctx, "hands", ())
        if getattr(single_hands, "hand_count", 0):
            parts.append(f"{single_hands.total_fingers} dedos extendidos confirmados")
        else:
            parts.append("manos no visibles")
        return ", ".join(parts)

    @property
    def history(self) -> tuple[str, ...]:
        return tuple(self._conversation_history)

    def reset(self) -> None:
        self._conversation_history.clear()
        self._visual_history.clear()
        self._greeted_this_visit = False
        self._faces_present = False
        self._reset_visual_stability()
