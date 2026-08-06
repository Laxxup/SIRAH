"""SIRAH Web Lab — Flask server with live camera, chat, voice control."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
from collections.abc import Coroutine, Iterator
from importlib.resources import files as resource_files
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

__all__ = ["create_app"]

logger = logging.getLogger(__name__)

_PACKAGE_WEB_DIR = Path(str(resource_files("sirah").joinpath("web")))
TEMPLATE_DIR = _PACKAGE_WEB_DIR / "templates"
STATIC_DIR = _PACKAGE_WEB_DIR / "static"


def _load_dotenv() -> None:
    for path in (".env", os.path.expanduser("~/SIRAH/.env")):
        if os.path.isfile(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        key, val = key.strip(), val.strip().strip("\"'")
                        if key and val:
                            os.environ.setdefault(key, val)


_system: Any = None
_vision_loop: Any = None
_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_lock = threading.Lock()
_latest_jpeg: bytes = b""
_vision_ctx_text: str = ""


def _run_loop(loop: asyncio.AbstractEventLoop, ready: threading.Event) -> None:
    asyncio.set_event_loop(loop)
    ready.set()
    loop.run_forever()


def _run_async[T](coro: Coroutine[Any, Any, T], timeout: float = 30.0) -> T:
    loop = _loop
    if loop is None or not loop.is_running():
        raise RuntimeError("SIRAH event loop is not running")

    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except BaseException:
        future.cancel()
        raise


def _parse_arecord_output(output: str) -> list[str]:
    return [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("card ") and ", device " in line
    ]


def _capture_devices() -> tuple[list[str], str | None]:
    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return [], "arecord no está instalado"
    except subprocess.TimeoutExpired:
        return [], "arecord tardó demasiado"

    devices = _parse_arecord_output(result.stdout)
    if result.returncode != 0:
        return devices, f"arecord terminó con código {result.returncode}"
    return devices, None


def _serialize_diagnostics(snapshot: Any) -> list[dict[str, str]]:
    return [
        {
            "id": str(component.id),
            "kind": component.id.kind.value,
            "name": component.id.name,
            "status": component.status.value,
            "detail": component.detail,
        }
        for component in snapshot.components
    ]


def _serialize_overlay(vision_loop: Any) -> dict[str, Any]:
    """Expose the latest local detections for the browser debug overlay."""
    if vision_loop is None:
        return {
            "ok": True,
            "active": False,
            "faces": [],
            "hands": [],
            "context": "",
        }

    context = getattr(vision_loop, "_latest_visual_ctx", None)
    faces = getattr(vision_loop, "_latest_faces", ())
    face_contexts = getattr(context, "face_contexts", ()) if context else ()
    serialized_faces = []
    for index, face in enumerate(faces):
        detail = face_contexts[index] if index < len(face_contexts) else None
        torso_bbox = getattr(detail, "torso_bbox", None)
        serialized_faces.append({
            "index": index + 1,
            "bbox": list(face.bbox),
            "confidence": face.confidence,
            "color": getattr(detail, "dominant_color", "desconocido"),
            "smiling": bool(getattr(detail, "smiling", False)),
            "smile_score": float(getattr(detail, "smile_score", 0.0)),
            "torso_bbox": list(torso_bbox) if torso_bbox is not None else None,
            "position": getattr(detail, "face_position", "centro"),
            "distance": getattr(detail, "face_distance", "media"),
        })

    hand_context = getattr(context, "hands", ()) if context else ()
    serialized_hands = [
        {
            "index": index + 1,
            "bbox": list(hand.bbox),
            "handedness": hand.handedness,
            "fingers": list(hand.fingers),
            "finger_count": hand.finger_count,
        }
        for index, hand in enumerate(getattr(hand_context, "hands", ()))
    ]
    return {
        "ok": True,
        "active": bool(getattr(vision_loop, "_running", False)),
        "faces": serialized_faces,
        "hands": serialized_hands,
        "context": getattr(vision_loop, "vision_description", ""),
    }


def create_app(
    intelligence_type: str = "laboratory",
    tts: str = "fake",
    piper_voice: str = "es_ES-sharvard-medium",
    profile_name: str = "DEV_LAPTOP",
    start_camera: bool = True,
) -> Flask:
    _load_dotenv()

    app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR))

    from sirah.factory import SystemProfile, build_system
    face_analyze_every = 3 if profile_name == "DEV_DISTRIBUTED" else 1

    global _loop, _loop_thread
    _loop = asyncio.new_event_loop()
    loop_ready = threading.Event()

    _loop_thread = threading.Thread(
        target=_run_loop,
        args=(_loop, loop_ready),
        daemon=True,
        name="sirah-asyncio",
    )
    _loop_thread.start()
    if not loop_ready.wait(timeout=2):
        raise RuntimeError("SIRAH event loop failed to start")

    async def _init_system() -> None:
        global _system, _vision_loop
        profile = getattr(SystemProfile, profile_name, SystemProfile.DEV_LAPTOP)
        _system = build_system(
            profile=profile,
            intelligence_type=intelligence_type,
            tts=tts,
            piper_voice=piper_voice,
        )
        await _system.orchestrator.start()

        _vision_loop = None
        if not start_camera:
            return

        from sirah.autonomy.person_tracker import PersonTracker
        from sirah.autonomy.vision_loop import VisionLoop

        _vision_loop = VisionLoop(
            orchestrator=_system.orchestrator,
            person_tracker=PersonTracker(),
            camera_device=0,
            idle_min=12,
            idle_max=30,
            silent_after_user=8.0,
            face_analyze_every=face_analyze_every,
            headless=True,
        )
        await _vision_loop.start()

        import time

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if _vision_loop._latest_jpeg:
                break
            await asyncio.sleep(0.1)

        print(f"[WebLab] Cámara {'OK' if _vision_loop._latest_jpeg else 'oscura/falló'} "
              f"({len(_vision_loop._latest_jpeg or b'')} bytes)")

    _run_async(_init_system(), timeout=10)

    def _refresh_visual_context() -> None:
        if _vision_loop is None:
            return
        try:
            _run_async(_vision_loop.refresh_context(), timeout=5)
        except Exception as exc:
            logger.warning("Fresh visual context failed: %s", exc)

    def _format_visual_context(text: str) -> str:
        if _vision_loop is None:
            return text
        desc = _vision_loop.vision_description or "sin datos visuales confirmados"
        return (
            f"[Contexto visual actual y completo: {desc}. "
            "Atribuye cada rasgo a la persona correspondiente. "
            "No afirmes manos, dedos, objetos o texto ausentes; "
            "si no aparecen en el contexto, di que no puedes verlo. "
            f"Mensaje del usuario: {text}"
        )

    def _message_with_visual_context(text: str) -> str:
        _refresh_visual_context()
        return _format_visual_context(text)

    @app.route("/")
    def index() -> str:
        return render_template("index.html")

    @app.route("/camera")
    def camera() -> Response:
        return Response(
            _generate_frames(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Accel-Buffering": "no",
            },
        )

    @app.route("/api/chat", methods=["POST"])
    def api_chat() -> Any:
        data = request.get_json()
        text = data.get("text", "").strip()
        if not text or _system is None:
            return jsonify({"ok": False, "error": "no text"}), 400

        full_text = _message_with_visual_context(text)
        if _vision_loop is not None:
            print(f"\n[Chat con visión]: {text}")

        def _run() -> dict:
            result = _run_async(
                _system.orchestrator.handle_text(full_text)
            )
            if _system.speech_output is not None:
                _run_async(_system.orchestrator.say(result.message.content))
            return {
                "ok": True,
                "response": result.message.content,
                "capability": result.decision.capability_name if result.decision else None,
            }

        return jsonify(_run())

    @app.route("/api/status")
    def api_status() -> Any:
        if _system is None:
            return jsonify({"ok": False, "error": "not started"}), 503
        snap = _run_async(asyncio.sleep(0, result=_system.orchestrator.snapshot))
        mood = None
        if _system.orchestrator.mood:
            mood = _system.orchestrator.mood.state.name
        return jsonify({
            "ok": True,
            "healthy": snap.healthy(),
            "components": len(snap.components),
            "diagnostics": _serialize_diagnostics(snap),
            "mood": mood,
            "vision_active": _vision_loop is not None,
        })

    @app.route("/api/overlay")
    def api_overlay() -> Any:
        return jsonify(_serialize_overlay(_vision_loop))

    @app.route("/api/mood", methods=["GET", "POST"])
    def api_mood() -> Any:
        if _system is None:
            return jsonify({"ok": False}), 503

        if request.method == "POST":
            data = request.get_json()
            state_name = data.get("state", "neutral").upper()
            from sirah.autonomy.mood_engine import MoodState

            try:
                state = getattr(MoodState, state_name)
            except AttributeError:
                return jsonify({"ok": False, "error": f"unknown state: {state_name}"}), 400

            _system.orchestrator.set_mood(state)
            return jsonify({"ok": True, "state": state.name})

        mood = _system.orchestrator.mood
        state = mood.state.name if mood else "NEUTRAL"
        return jsonify({"ok": True, "state": state})

    @app.route("/api/vision", methods=["POST"])
    def api_vision() -> Any:
        global _vision_loop

        data = request.get_json()
        action = data.get("action", "status")

        if action == "on":
            if _vision_loop is not None:
                return jsonify({"ok": True, "status": "already active"})
            from sirah.autonomy.person_tracker import PersonTracker
            from sirah.autonomy.vision_loop import VisionLoop

            _vision_loop = VisionLoop(
                orchestrator=_system.orchestrator,
                person_tracker=PersonTracker(),
                camera_device=0,
                idle_min=12.0,
                idle_max=30.0,
                silent_after_user=8.0,
                face_analyze_every=face_analyze_every,
                headless=True,
            )
            _run_async(_vision_loop.start())
            return jsonify({"ok": True, "status": "active"})

        elif action == "off":
            if _vision_loop is not None:
                _run_async(_vision_loop.stop())
                _vision_loop = None
            return jsonify({"ok": True, "status": "inactive"})

        return jsonify({"ok": True, "status": "active" if _vision_loop else "inactive"})

    @app.route("/api/mic")
    def api_mic() -> Any:
        devices, error = _capture_devices()
        return jsonify({
            "ok": error is None,
            "available": bool(devices),
            "devices": devices,
            "error": error,
        })

    @app.route("/api/autonomy")
    def api_autonomy() -> Any:
        if _vision_loop is None:
            return jsonify({
                "ok": True,
                "active": False,
                "messages": [],
                "vision_description": "",
            })
        return jsonify({
            "ok": True,
            "active": _vision_loop._running,
            "messages": list(_vision_loop.history),
            "vision_description": _vision_loop.vision_description,
        })

    @app.route("/api/upload_frame", methods=["POST"])
    def api_upload_frame() -> Any:
        global _latest_jpeg

        data = request.get_data()
        if not data or _vision_loop is None:
            return jsonify({"ok": False}), 400

        with _lock:
            _latest_jpeg = data

        import cv2
        import numpy as np

        nparr = np.frombuffer(data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is not None and _vision_loop is not None:
            frame = cv2.flip(frame, 1)
            _vision_loop._latest_frame = frame
        return jsonify({"ok": True})

    @app.route("/api/listen", methods=["POST"])
    def api_listen() -> Any:
        if _system is None:
            return jsonify({"ok": False}), 503

        audio_file = request.files.get("audio")
        audio_data = audio_file.read() if audio_file else None

        async def _listen(audio: bytes | None) -> dict:
            if audio is None:
                try:
                    from sirah.voice.mic_capture import MicCapture
                except ImportError:
                    return {"ok": False, "text": "", "response": "Micrófono no disponible."}

                mic = MicCapture()
                await mic.start()
                try:
                    audio = await mic.record(duration_s=5.0)
                finally:
                    await mic.stop()

            if not audio or len(audio) < 500:
                return {"ok": True, "text": "", "response": "No escuché nada."}

            audio = _prepare_audio(audio)
            if audio is None:
                return {
                    "ok": True,
                    "text": "",
                    "response": "No pude leer el audio. ¿Está disponible ffmpeg?",
                }

            from sirah.voice.stt_whisper import WhisperSTT

            stt = WhisperSTT(model_size="tiny", language="es")
            await stt.start()
            try:
                event = await stt.transcribe(audio)
            except Exception:
                return {
                    "ok": True,
                    "text": "",
                    "response": "No pude transcribir el audio.",
                }
            finally:
                await stt.stop()

            text = event.text.strip()
            if not text:
                return {"ok": True, "text": "", "response": "No entendí lo que dijiste."}

            if _vision_loop is not None:
                _vision_loop.mark_user_spoke()

            if _vision_loop is not None:
                await _vision_loop.refresh_context()
            result = await _system.orchestrator.handle_text(
                _format_visual_context(text)
            )
            if _system.speech_output is not None:
                await _system.orchestrator.say(result.message.content)

            return {"ok": True, "text": text, "response": result.message.content}

        return jsonify(_run_async(_listen(audio_data)))

    @app.route("/api/history")
    def api_history() -> Any:
        if _system is None:
            return jsonify({"ok": False}), 503
        ctx = _system.orchestrator.context
        msgs = [{"role": m.role, "content": m.content} for m in ctx.messages]
        return jsonify({"ok": True, "messages": msgs})

    return app


def _generate_frames() -> Iterator[bytes]:
    import time

    previous_jpeg: bytes | None = None
    while True:
        jpeg_data = None
        with _lock:
            jpeg_data = _latest_jpeg

        if not jpeg_data and _vision_loop is not None:
            jpeg_data = _vision_loop._latest_jpeg

        if jpeg_data and jpeg_data != previous_jpeg:
            previous_jpeg = jpeg_data
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg_data + b"\r\n"
            )
        else:
            time.sleep(0.005)


def _convert_to_wav(data: bytes) -> bytes | None:
    import os
    import subprocess
    import tempfile

    if data[:4] == b"RIFF":
        return data

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    wav_path = tmp_path + ".wav"
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_path, "-ar", "16000", "-ac", "1",
             "-f", "wav", wav_path],
            capture_output=True, timeout=15,
        )
        if result.returncode == 0 and os.path.exists(wav_path):
            with open(wav_path, "rb") as f:
                return f.read()
    except (FileNotFoundError, Exception):
        pass
    finally:
        for p in [tmp_path, wav_path]:
            if os.path.exists(p):
                os.unlink(p)

    return None


def _prepare_audio(data: bytes) -> bytes | None:
    """Return PCM WAV bytes for Whisper, converting browser audio when needed."""
    if data[:4] == b"RIFF":
        return data
    return _convert_to_wav(data)


def main() -> None:
    import signal

    def _cleanup(*args: object) -> None:
        print("\nApagando SIRAH Web Lab...")
        if _vision_loop is not None:
            _run_async(_vision_loop.stop())
        if _system is not None:
            _run_async(_system.orchestrator.stop())
        loop = _loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if _loop_thread is not None:
            _loop_thread.join(timeout=2)
        if loop is not None:
            loop.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)
    import argparse

    parser = argparse.ArgumentParser(description="SIRAH Web Lab")
    parser.add_argument("--intel", default="laboratory")
    parser.add_argument("--tts", default="fake")
    parser.add_argument("--voice", default="es_ES-sharvard-medium")
    parser.add_argument("--profile", default="DEV_LAPTOP")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    app = create_app(
        intelligence_type=args.intel,
        tts=args.tts,
        piper_voice=args.voice,
        profile_name=args.profile,
    )
    print("\n╔══════════════════════════════════════╗")
    print("║      SIRAH WEB LAB                   ║")
    print(f"║  Abre http://localhost:{args.port}           ║")
    print("╚══════════════════════════════════════╝\n")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
