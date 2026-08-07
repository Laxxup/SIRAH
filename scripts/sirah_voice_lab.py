"""SIRAH voice lab: eyes follow your face while you talk and she answers aloud.

SIRAH is SELF-AWARE: she knows her own internal state — eye position, face
detected, clothing color, smile, distance, lighting — and mentions it naturally.
Groq gets that state plus recent conversation history, with creative freedom and
autonomy (no repetitive "how can I help you"). Without GROQ_API_KEY she falls
back to an echo mode.

Pipeline (each turn):
  1. Eyes follow your face via serial (background task exposes full state).
  2. Record Ns from the mic (arecord).
  3. Whisper transcribes (faster-whisper, base, es).
  4. Intelligence responds (Groq if GROQ_API_KEY set, else echo), aware of SIRAH's body.
  5. Piper TTS (es_ES-sharvard-medium) speaks via aplay.

Run:
  PYTHONPATH=src .venv/bin/python scripts/sirah_voice_lab.py
  GROQ_API_KEY=sk-... PYTHONPATH=src .venv/bin/python scripts/sirah_voice_lab.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

import cv2

from sirah.intelligence.groq_adapter import GroqIntelligence
from sirah.intelligence.port import IntelligencePort
from sirah.perception.mediapipe_vision import MediaPipeVision
from sirah.types import ConversationMessage, DecisionType, IntelligenceDecision, IntelligenceRequest, IntelligenceResponse
from sirah.voice.mic_capture import MicCapture
from sirah.voice.stt_whisper import WhisperSTT
from sirah.voice.tts_piper import AplayPlayer, PiperTTS

VOICE_DIR = Path("/home/laxxup/.local/share/piper/voices")
MODEL_PATH = VOICE_DIR / "es_ES-sharvard-medium.onnx"
CONFIG_PATH = VOICE_DIR / "es_ES-sharvard-medium.onnx.json"
EVIDENCE_DIR = Path("/tmp/sirah-evidence")
DETECT_EVERY = 3
SMOOTHING = 0.30
X_LEFT = 14
X_RIGHT = 90
MAX_HISTORY = 8
SPEECH_RMS = 600
SILENCE_CHUNKS_TO_STOP = 8
SILENCE_CHUNK_S = 0.1


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def servo_from_face_x(face_x: float, mirror: bool) -> int:
    mirrored = (1.0 - face_x) if mirror else face_x
    return int(round(X_LEFT + clamp(mirrored, 0.0, 1.0) * (X_RIGHT - X_LEFT)))


def describe_position(face_x: float) -> str:
    if face_x < 0.30:
        return "a tu izquierda"
    if face_x > 0.70:
        return "a tu derecha"
    return "frente a ti"


def build_self_state(perception: dict) -> str:
    """Describe SIRAH's own body + what she perceives, in natural Spanish."""
    parts = []
    if perception.get("face_detected"):
        pos = perception.get("face_x")
        if pos is not None:
            parts.append(f"te tengo {describe_position(pos)} (face_x={pos:.2f})")
            parts.append("mis ojos te están siguiendo")
        color = perception.get("dominant_color")
        if color and color != "desconocido":
            parts.append(f"detecto tu ropa de color {color}")
        smile = perception.get("smiling")
        if smile is True:
            parts.append("estás sonriendo")
        elif smile is False:
            parts.append("tienes expresión neutra")
        dist = perception.get("face_distance")
        if dist:
            parts.append(f"estás {dist}")
        light = perception.get("lighting")
        if light and light != "normal":
            parts.append(f"la luz está {light}")
        hands = perception.get("hands", 0)
        if hands:
            parts.append(f"veo {hands} mano(s)")
    else:
        parts.append("no tengo a nadie frente a mí")
        parts.append("mis ojos están centrados, esperando")
    return "; ".join(parts) if parts else "estado desconocido"


class SelfAwareIntelligence:
    """Wraps any intelligence and injects SIRAH's self-state + memory into every request."""

    def __init__(self, inner: IntelligencePort, state_provider, history_limit: int = MAX_HISTORY) -> None:
        self._inner = inner
        self._state = state_provider
        self._history: list[tuple[str, str]] = []
        self._history_limit = history_limit
        self._turn = 0

    async def health(self) -> bool:
        return await self._inner.health()

    def _system_prompt(self, perception: dict) -> str:
        self_state = build_self_state(self._state())
        recent = ""
        if self._history:
            lines = [f"  - el usuario dijo: '{u}' -> respondiste: '{s}'" for u, s in self._history[-4:]]
            recent = "Conversación reciente (NO repitas lo que ya dijiste):\n" + "\n".join(lines)

        return (
            "Eres SIRAH, un robot social con cuerpo físico real. "
            "Tienes ojos con servos que mueven la mirada horizontalmente, "
            "parpadeas de forma natural, una cámara que detecta rostros, colores, "
            "sonrisas y micrófono. Eres autónoma, creativa y expresiva.\n\n"
            "REGLAS:\n"
            "- NUNCA digas '¿en qué puedo ayudarte?' ni fórmulas repetitivas. "
            "Habla con libertad: comenta, pregunta, observa, bromea, reflexiona.\n"
            "- Usa tu estado corporal en lo que dices: menciona si te mueves, "
            "si te siguen con la mirada, si detectas colores o sonrisas. "
            "Ej: '¿No ves cómo te miro?', 'Veo que traes algo azul'.\n"
            "- Sé breve pero natural (2-3 frases). Varía tu tono y temas.\n"
            "- Responde siempre en español, primera persona, personalidad cálida.\n\n"
            f"TU ESTADO ACTUAL:\n{self_state}\n\n"
            f"{recent}\n"
            "Responde a lo que el usuario acaba de decir, integrando tu estado de forma natural."
        )

    async def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        self._turn += 1
        perception = self._state()
        system_text = self._system_prompt(perception)

        request.messages.insert(0, ConversationMessage(role="system", content=system_text))
        response = await self._inner.decide(request)

        user_text = ""
        for msg in request.messages:
            if getattr(msg, "role", "") == "user":
                user_text = getattr(msg, "content", "")
        answer = (response.decision.text_response if response.decision else "").strip()
        if answer and user_text:
            self._history.append((user_text, answer))
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit:]
        return response


class EchoIntelligence:
    """Fallback that acknowledges what was said without an API key."""

    async def health(self) -> bool:
        return True

    async def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        user_text = ""
        for msg in request.messages:
            if getattr(msg, "role", "") == "user":
                user_text = getattr(msg, "content", "")
        user_text = (user_text or "").strip()
        if not user_text:
            answer = "Te escucho, pero no capturé nada. ¿Puedes repetir?"
        else:
            answer = f"Te escucho decir: '{user_text}'. Sin Groq no puedo conversar de verdad, pero estoy aquí."
        return IntelligenceResponse(
            raw_text=answer,
            decision=IntelligenceDecision(decision_type=DecisionType.CONVERSATION, text_response=answer, confidence=0.6),
            latency_ms=1.0,
            model="echo",
        )


async def eye_tracker(camera: str, serial_port: str, mirror: bool, state: dict) -> None:
    """Detect face, command eye servo, and publish full perception state."""
    try:
        import serial_asyncio
        _, writer = await serial_asyncio.open_serial_connection(url=serial_port, baudrate=115200)
    except Exception as exc:
        logging.warning("eye_tracker sin serial: %s", exc)
        return

    cap = cv2.VideoCapture(camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    vision = MediaPipeVision()
    await vision.start()

    servo: Optional[int] = None
    frames_since_detection = DETECT_EVERY
    try:
        while True:
            ok, frame = await asyncio.to_thread(cap.read)
            if not ok:
                await asyncio.sleep(0.05)
                continue
            frames_since_detection += 1
            if frames_since_detection >= DETECT_EVERY:
                frames_since_detection = 0
                context = await vision.analyze(frame)
                faces = await vision.detect(frame)
                if faces and context.face_contexts:
                    largest_face = max(faces, key=lambda f: float(f.bbox[2]) * float(f.bbox[3]))
                    ctx = context.face_contexts[0]
                    cx = float(largest_face.bbox[0]) + float(largest_face.bbox[2]) / 2.0
                    state["face_x"] = cx
                    state["face_detected"] = True
                    state["dominant_color"] = ctx.dominant_color
                    state["smiling"] = ctx.smiling
                    state["face_distance"] = ctx.face_distance
                    state["lighting"] = ctx.lighting
                    hands = getattr(context, "hands", ())
                    state["hands"] = getattr(hands, "hand_count", 0)
                    target = servo_from_face_x(cx, mirror)
                    servo = target if servo is None else int(round(servo + (target - servo) * SMOOTHING))
                    state["servo_x"] = servo
                    writer.write((f"X {servo}\n").encode())
                else:
                    for k in ("face_x", "face_detected", "dominant_color", "smiling", "face_distance", "hands", "servo_x"):
                        state[k] = None if k != "face_detected" else False
                    state["face_detected"] = False
                    servo = None
                    writer.write(b"CENTER\n")
            await asyncio.sleep(0.01)
    finally:
        cap.release()
        await vision.stop()
        writer.close()


def build_intelligence(state: dict) -> IntelligencePort:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    inner: IntelligencePort
    if key:
        logging.info("inteligencia: Groq (llama-3.3-70b-versatile) + autoconciencia")
        inner = GroqIntelligence(api_key=key, temperature=0.9, max_tokens=200)
    else:
        logging.info("inteligencia: eco (exporta GROQ_API_KEY para Groq real)")
        inner = EchoIntelligence()
    return SelfAwareIntelligence(inner, lambda: dict(state))


async def _record_voice_activity(mic: MicCapture, target_s: float, max_s: float) -> object:
    """Record until the user stops speaking (VAD) or max_s is reached.

    Chunks audio while monitoring RMS; once speech is seen, stop after a run of
    silence chunks. Falls back to fixed target_s if no speech is detected early.
    """
    from sirah.voice.diagnostics import analyze_pcm, CapturedAudio

    t0 = asyncio.get_event_loop().time()
    chunks: list[bytes] = []
    saw_speech = False
    silent_streak = 0
    chunk_target = min(target_s, max_s)
    try:
        while True:
            elapsed = asyncio.get_event_loop().time() - t0
            chunk = await mic.read_chunk(timeout=0.3)
            final = mic._raise_if_exited()  # type: ignore[attr-defined]
            if chunk:
                chunks.append(chunk)
            if final:
                chunks.append(final)
            if not chunk:
                await asyncio.sleep(0.02)
            raw = b"".join(chunks)
            metrics = analyze_pcm(raw)
            if metrics.rms > SPEECH_RMS:
                saw_speech = True
                silent_streak = 0
            elif saw_speech:
                silent_streak += 1
            if saw_speech and silent_streak >= SILENCE_CHUNKS_TO_STOP:
                break
            if elapsed >= max_s:
                break
            if not saw_speech and elapsed >= chunk_target:
                break
    except Exception as exc:
        logging.warning("record_vad excepcion: %s", exc)
    raw = b"".join(chunks)
    if not raw:
        raw = b"\x00\x00"
    metrics = analyze_pcm(raw)
    wav_data = mic._raw_to_wav(raw)  # type: ignore[attr-defined]
    return CapturedAudio(
        data=wav_data,
        sample_rate=metrics.sample_rate,
        channels=metrics.channels,
        sample_width=metrics.sample_width,
        duration_ms=metrics.duration_ms,
        metrics=metrics,
    )


def _perception_summary(state: dict) -> str:
    if not state.get("face_detected"):
        return "sin cara"
    bits = [f"face_x={state.get('face_x', 0):.2f}"]
    if state.get("dominant_color"):
        bits.append(state["dominant_color"])
    if state.get("smiling") is not None:
        bits.append("sonrisa" if state["smiling"] else "neutral")
    return ", ".join(bits)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    log = logging.getLogger("sirah_voice_lab")

    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default="/dev/video2")
    parser.add_argument("--serial", default="/dev/ttyUSB0")
    parser.add_argument("--mic", default="hw:1,0")
    parser.add_argument("--speaker", default="default")
    parser.add_argument("--record-s", type=float, default=3.0)
    parser.add_argument("--max-record-s", type=float, default=6.0,
                        help="max recording length; --record-s sets the target")
    parser.add_argument("--no-eyes", action="store_true")
    parser.add_argument("--mirror", default="true")
    args = parser.parse_args()
    mirror_on = args.mirror.lower() in {"1", "true", "yes", "on"}

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    state: dict = {"face_detected": False}
    eye_task = None
    if not args.no_eyes:
        eye_task = asyncio.create_task(eye_tracker(args.camera, args.serial, mirror_on, state))
        log.info("ojos iniciados en %s (mirror=%s)", args.serial, mirror_on)

    log.info("cargando Whisper (tiny, es) mas rapido en CPU...")
    whisper = WhisperSTT(model_size="tiny", language="es", timeout_s=30.0)
    await whisper.start()
    log.info("Whisper listo: %s", await whisper.health())

    if not MODEL_PATH.is_file():
        raise SystemExit(f"modelo Piper no encontrado: {MODEL_PATH}")
    player = AplayPlayer(output_device=args.speaker, timeout_s=15.0)
    tts = PiperTTS(model_path=MODEL_PATH, config_path=CONFIG_PATH, player=player)
    await tts.start()
    log.info("Piper listo: modelo %s", MODEL_PATH.name)

    intelligence = build_intelligence(state)

    turn = 0
    try:
        mic = MicCapture(device=args.mic)
        await mic.start()
        while True:
            turn += 1
            log.info("=== TURNO %d | ojos: %s | grabando hasta callar en %s ===",
                     turn, _perception_summary(state), args.mic)
            print(f"\n🎤 ESCUCHANDO... (habla; paro solo cuando calles; max {args.max_record_s}s)")
            try:
                captured = await _record_voice_activity(
                    mic, target_s=args.record_s, max_s=args.max_record_s
                )
            except Exception as exc:
                log.warning("captura fallo: %s", exc)
                continue
            log.info("captura: %.1fs, rms=%d, silent=%s", captured.duration_ms / 1000,
                     captured.metrics.rms, captured.metrics.is_silent)

            if captured.metrics.is_silent:
                log.info("silencio -> no transcribo")
                continue

            print("🧠 TRANSCRIBIENDO...")
            try:
                event = await whisper.transcribe(captured.data, turn_id=f"turn-{turn}")
            except Exception as exc:
                log.warning("transcripcion fallo: %s", exc)
                print("⚠️ no pude transcribir, intenta de nuevo")
                continue
            text = (event.text or "").strip()
            log.info("transcripcion: '%s' (conf=%.2f)", text, event.confidence)
            print(f"🗣️  TÚ: {text}")

            if not text:
                log.info("vacio -> omito")
                continue

            if text.lower().rstrip(".!?") in {"salir", "exit", "terminar", "fin", "apagar"}:
                await tts.speak("Hasta luego. Fue un gusto hablar contigo. Aquí estaré.")
                break

            print("💭 PENSANDO...")
            request = IntelligenceRequest(messages=[], max_tokens=200, temperature=0.9)
            request.messages.append(ConversationMessage(role="user", content=text))
            try:
                response = await intelligence.decide(request)
            except Exception as exc:
                log.warning("inteligencia fallo: %s", exc)
                print("⚠️ fallo el pensamiento, intenta de nuevo")
                continue
            answer = (response.decision.text_response if response.decision else "").strip()
            log.info("respuesta (%s): '%s'", response.model, answer)
            print(f"🤖 SIRAH: {answer}")

            if answer:
                print("🔊 HABLANDO...")
                try:
                    await tts.speak(answer)
                except Exception as exc:
                    log.warning("voz fallo: %s", exc)
    except KeyboardInterrupt:
        log.info("interrupcion por teclado")
    finally:
        await mic.stop()
        await whisper.stop()
        await tts.stop()
        if eye_task is not None:
            eye_task.cancel()
    log.info("laboratorio detenido")


if __name__ == "__main__":
    asyncio.run(main())
