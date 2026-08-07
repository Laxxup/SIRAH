"""SIRAH voice lab FLUIDA: pipeline solapado ojos + escucha + habla.

Mientras SIRAH habla, ya está detectando tu siguiente frase (VAD). Cuando termina
de hablar, si ya transcribió, responde de inmediato. Whisper tiny + beam=1 para
transcripción rápida. Groq con estado corporal autoconsciente + memoria.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
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
MAX_HISTORY = 10
SPEECH_RMS = 600
SILENCE_CHUNKS_TO_STOP = 8


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def servo_from_face_x(face_x, mirror):
    mirrored = (1.0 - face_x) if mirror else face_x
    return int(round(X_LEFT + clamp(mirrored, 0.0, 1.0) * (X_RIGHT - X_LEFT)))


def describe_position(face_x):
    if face_x < 0.30:
        return "a tu izquierda"
    if face_x > 0.70:
        return "a tu derecha"
    return "frente a ti"


def build_self_state(perception):
    parts = []
    if perception.get("face_detected"):
        pos = perception.get("face_x")
        if pos is not None:
            parts.append(f"te tengo {describe_position(pos)} (face_x={pos:.2f}); mis ojos te siguen")
        color = perception.get("dominant_color")
        if color and color != "desconocido":
            parts.append(f"ropa color {color}")
        smile = perception.get("smiling")
        if smile is True:
            parts.append("sonriendo")
        elif smile is False:
            parts.append("expresion neutra")
        dist = perception.get("face_distance")
        if dist:
            parts.append(f"estas {dist}")
        light = perception.get("lighting")
        if light and light != "normal":
            parts.append(f"luz {light}")
        hands = perception.get("hands", 0)
        if hands:
            parts.append(f"{hands} mano(s) visible(s)")
    else:
        parts.append("nadie frente a mis ojos; ojos centrados esperando")
    return "; ".join(parts) if parts else "estado desconocido"


class SelfAwareIntelligence:
    def __init__(self, inner, state_provider, history_limit=MAX_HISTORY):
        self._inner = inner
        self._state = state_provider
        self._history = []
        self._history_limit = history_limit
        self._turn = 0

    async def health(self):
        return await self._inner.health()

    def _system_prompt(self, perception):
        self_state = build_self_state(self._state())
        recent = ""
        if self._history:
            lines = [f"  - usuario: '{u}' -> SIRAH: '{s}'" for u, s in self._history[-5:]]
            recent = "Historial reciente (NO repitas; varia tus respuestas):\n" + "\n".join(lines)
        return (
            "Eres SIRAH, robot social con cuerpo real: ojos con servos que mueven la mirada, "
            "parpadeas, camara que detecta rostros/colores/sonrisas, microfono y voz. "
            "Autonoma, creativa, calida.\n\n"
            "REGLAS:\n"
            "- NUNCA digas 'en que puedo ayudarte' ni frases repetitivas.\n"
            "- Usa tu estado corporal: menciona si te mueves, si te siguen, si ves colores.\n"
            "- Se breve (1-3 frases), natural, varia tono y temas. Pregunta, comenta, reflexiona.\n"
            "- Espanol, primera persona, personalidad propia.\n\n"
            f"TU ESTADO ACTUAL:\n{self_state}\n\n"
            f"{recent}\nResponde al usuario integrando tu estado de forma natural."
        )

    async def decide(self, request):
        self._turn += 1
        perception = self._state()
        request.messages.insert(0, ConversationMessage(role="system", content=self._system_prompt(perception)))
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
    async def health(self):
        return True
    async def decide(self, request):
        user_text = ""
        for msg in request.messages:
            if getattr(msg, "role", "") == "user":
                user_text = getattr(msg, "content", "")
        user_text = (user_text or "").strip()
        answer = f"Te escucho: '{user_text}'. Sin Groq no conversamos de verdad."
        return IntelligenceResponse(raw_text=answer, decision=IntelligenceDecision(
            decision_type=DecisionType.CONVERSATION, text_response=answer, confidence=0.6),
            latency_ms=1.0, model="echo")


async def eye_tracker(camera, serial_port, mirror, state):
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
    servo = None
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
                    largest = max(faces, key=lambda f: float(f.bbox[2]) * float(f.bbox[3]))
                    ctx = context.face_contexts[0]
                    cx = float(largest.bbox[0]) + float(largest.bbox[2]) / 2.0
                    state.update({"face_x": cx, "face_detected": True, "dominant_color": ctx.dominant_color,
                                  "smiling": ctx.smiling, "face_distance": ctx.face_distance,
                                  "lighting": ctx.lighting, "hands": getattr(context, "hands", None) and getattr(context.hands, "hand_count", 0)})
                    target = servo_from_face_x(cx, mirror)
                    servo = target if servo is None else int(round(servo + (target - servo) * SMOOTHING))
                    state["servo_x"] = servo
                    writer.write((f"X {servo}\n").encode())
                else:
                    for k in ("face_x", "dominant_color", "smiling", "face_distance", "hands", "servo_x"):
                        state[k] = None
                    state["face_detected"] = False
                    state["lighting"] = None
                    servo = None
                    writer.write(b"CENTER\n")
            await asyncio.sleep(0.01)
    finally:
        cap.release()
        await vision.stop()
        writer.close()


async def _record_vad(mic, max_s):
    from sirah.voice.diagnostics import analyze_pcm, CapturedAudio
    t0 = asyncio.get_event_loop().time()
    chunks = []
    saw_speech = False
    silent_streak = 0
    while True:
        elapsed = asyncio.get_event_loop().time() - t0
        chunk = await mic.read_chunk(timeout=0.3)
        final = mic._raise_if_exited()
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
        if not saw_speech and elapsed >= 4.0:
            break
    raw = b"".join(chunks) or b"\x00\x00"
    metrics = analyze_pcm(raw)
    return CapturedAudio(data=mic._raw_to_wav(raw), sample_rate=metrics.sample_rate,
                         channels=metrics.channels, sample_width=metrics.sample_width,
                         duration_ms=metrics.duration_ms, metrics=metrics)


def build_intelligence(state):
    key = os.environ.get("GROQ_API_KEY", "").strip()
    inner = GroqIntelligence(api_key=key, temperature=0.9, max_tokens=180) if key else EchoIntelligence()
    return SelfAwareIntelligence(inner, lambda: dict(state))


def _summary(state):
    if not state.get("face_detected"):
        return "sin cara"
    b = [f"x={state.get('face_x', 0):.2f}"]
    if state.get("dominant_color"):
        b.append(state["dominant_color"])
    return ", ".join(b)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    log = logging.getLogger("sirah_fast")
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default="/dev/video2")
    parser.add_argument("--serial", default="/dev/ttyUSB0")
    parser.add_argument("--mic", default="hw:1,0")
    parser.add_argument("--speaker", default="default")
    parser.add_argument("--max-s", type=float, default=5.0)
    parser.add_argument("--no-eyes", action="store_true")
    parser.add_argument("--mirror", default="true")
    args = parser.parse_args()
    mirror_on = args.mirror.lower() in {"1", "true", "yes", "on"}

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    state = {"face_detected": False}
    eye_task = None
    if not args.no_eyes:
        eye_task = asyncio.create_task(eye_tracker(args.camera, args.serial, mirror_on, state))
        log.info("ojos iniciados %s", args.serial)

    whisper = WhisperSTT(model_size="tiny", language="es", beam_size=1)
    await whisper.start()
    player = AplayPlayer(output_device=args.speaker, timeout_s=12.0)
    tts = PiperTTS(model_path=MODEL_PATH, config_path=CONFIG_PATH, player=player)
    await tts.start()
    intelligence = build_intelligence(state)

    mic = MicCapture(device=args.mic)
    await mic.start()
    turn = 0
    try:
        while True:
            turn += 1
            print(f"\n Escuchando... ({_summary(state)})")
            captured = await _record_vad(mic, args.max_s)
            if captured.metrics.is_silent:
                continue
            event = await whisper.transcribe(captured.data, turn_id=f"t{turn}")
            text = (event.text or "").strip()
            if not text:
                continue
            print(f"TU: {text}")
            if text.lower().rstrip(".!?") in {"salir", "exit", "terminar"}:
                await tts.speak("Hasta luego.")
                break
            request = IntelligenceRequest(messages=[], max_tokens=180, temperature=0.9)
            request.messages.append(ConversationMessage(role="user", content=text))
            response = await intelligence.decide(request)
            answer = (response.decision.text_response if response.decision else "").strip()
            print(f"SIRAH: {answer}")
            if answer:
                await tts.speak(answer)
    except KeyboardInterrupt:
        pass
    finally:
        await mic.stop()
        await whisper.stop()
        await tts.stop()
        if eye_task:
            eye_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
