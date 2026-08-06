"""Interactive Laboratory Console for SIRAH.

Text-based conversational interface. Optional webcam preview with face overlay.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import suppress
from time import monotonic
from typing import TYPE_CHECKING

from sirah.factory import SystemAssembly, SystemProfile, build_system

if TYPE_CHECKING:
    from sirah.autonomy.vision_loop import VisionLoop

__all__ = ["LaboratoryConsole"]


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

__all__ = ["LaboratoryConsole"]

logger = logging.getLogger(__name__)

BANNER = """
╔══════════════════════════════════════╗
║         SIRAH LABORATORY v2         ║
║   Sistema Inteligente Robótico      ║
║   de Asistencia Humana              ║
╚══════════════════════════════════════╝
"""

HELP_TEXT = """
Comandos disponibles:
  /help       Este mensaje
  /status     Estado del sistema
  /camera     Mostrar preview de webcam (5s)
  /faces      Mostrar detección de rostros
  /history    Ver historial de conversación
  /silent     Silenciar iniciativa automática
  /loud       Reactivar iniciativa
  /listen    Escuchar micrófono y transcribir (5s)
  /stt       Activar/desactivar escucha continua (on/off)
  /vision    Activar/desactivar cámara con detección facial (on/off)
  /mood       Ver/cambiar estado de ánimo (happy, neutral, curious, tired, concerned)
  /autonomy   Activar/desactivar autonomía (on/off)
  /profile    Cambiar perfil (dev_laptop, dev_distributed)
  /intel      Cambiar inteligencia (fake, laboratory, scripted, groq)
  /quit       Salir
  Ctrl+C      Salir
"""


class LaboratoryConsole:
    def __init__(
        self,
        profile: SystemProfile = SystemProfile.DEV_LAPTOP,
        intelligence_type: str = "laboratory",
        tts: str = "fake",
        piper_voice: str = "es_ES-sharvard-medium",
        enable_vision: bool = False,
    ) -> None:
        self._profile = profile
        self._intelligence_type = intelligence_type
        self._tts = tts
        self._piper_voice = piper_voice
        self._enable_vision = enable_vision
        self._system: SystemAssembly | None = None
        self._vision_loop: VisionLoop | None = None
        self._running = False
        self._stt_task: asyncio.Task[object] | None = None
        self._stt_active = False
        self._setup_logging()

    def _setup_logging(self) -> None:
        logging.basicConfig(
            level=logging.WARNING,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    async def run(self) -> None:
        print(BANNER)
        self._system = build_system(
            profile=self._profile,
            intelligence_type=self._intelligence_type,
            tts=self._tts,
            piper_voice=self._piper_voice,
        )
        assert self._system is not None
        await self._system.orchestrator.start()
        await self._system.situational.start() if self._system.situational else None

        if self._enable_vision:
            await self._start_vision()

        self._running = True
        print(f"Perfil: {self._profile.name} | Inteligencia: {self._intelligence_type} | TTS: {self._tts}")
        print(HELP_TEXT)

        while self._running:
            try:
                user_input = await self._read_input()
                if user_input is None:
                    break
                if not user_input.strip():
                    continue
                await self._dispatch(user_input.strip())
            except KeyboardInterrupt:
                print("\nSaliendo...")
                break
            except Exception as exc:
                logger.exception("Console error")
                print(f"Error: {exc}")

        await self._system.orchestrator.stop()
        if self._stt_task is not None:
            self._stt_active = False
            self._stt_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stt_task
        if self._vision_loop is not None:
            await self._vision_loop.stop()
        await self._system.situational.stop() if self._system.situational else None
        print("SIRAH apagado.")

    async def _read_input(self) -> str | None:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, lambda: input("\nTú > "))
        except (EOFError, KeyboardInterrupt):
            return None

    async def _dispatch(self, text: str) -> None:
        if text.startswith("/"):
            await self._handle_command(text[1:].strip())
            return

        if self._vision_loop is not None:
            self._vision_loop.mark_user_spoke()

        assert self._system is not None

        t0 = monotonic()
        result = await self._system.orchestrator.handle_text(text)
        elapsed = (monotonic() - t0) * 1000

        print(f"\nSIRAH ({elapsed:.0f}ms): {result.message.content}")

        if result.decision and result.decision.capability_name:
            print(f"  [acción: {result.decision.capability_name}]")

        if self._system.speech_output is not None:
            asyncio.create_task(self._system.orchestrator.say(result.message.content))

    async def _handle_command(self, cmd: str) -> None:
        parts = cmd.split()
        cmd_name = parts[0].lower()
        args = parts[1:]

        assert self._system is not None

        if cmd_name == "help":
            print(HELP_TEXT)

        elif cmd_name == "status":
            snap = self._system.orchestrator.snapshot
            print(f"\nEstado del sistema ({'OK' if snap.healthy() else 'DEGRADADO'}):")
            for c in snap.components:
                print(f"  {c.id} → {c.status.value}" + (f" ({c.detail})" if c.detail else ""))

        elif cmd_name == "camera":
            print("Previsualizando cámara 5s...")
            try:
                await self._camera_preview(duration=5.0)
            except Exception as exc:
                print(f"Error de cámara: {exc}")

        elif cmd_name == "faces":
            await self._detect_faces()

        elif cmd_name == "history":
            ctx = self._system.orchestrator.context
            print("\nHistorial de conversación:")
            for msg in ctx.messages:
                print(f"  [{msg.role}]: {msg.content[:80]}")

        elif cmd_name == "silent":
            if self._system.situational:
                self._system.situational._silent = True
                print("Iniciativa silenciada.")
            else:
                print("Sin coordinador situacional.")

        elif cmd_name == "loud":
            if self._system.situational:
                self._system.situational._silent = False
                print("Iniciativa activada.")
            else:
                print("Sin coordinador situacional.")

        elif cmd_name == "mood":
            if args:
                from sirah.autonomy.mood_engine import MoodState

                state_map = {s.name.lower(): s for s in MoodState}
                state = state_map.get(args[0].lower())
                if state:
                    self._system.orchestrator.set_mood(state)
                    print(f"Mood: {state.name}")
                else:
                    print(f"Estados: {', '.join(s.name.lower() for s in MoodState)}")
            else:
                m = self._system.orchestrator.mood
                if m:
                    print(f"Mood actual: {m.state.name}")
                else:
                    print("MoodEngine no activo (usa build_system con mood=True)")

        elif cmd_name == "autonomy":
            action = args[0].lower() if args else "status"
            if action == "on":
                if self._system.situational:
                    self._system.situational._silent = False
                print("Autonomía ACTIVADA")
            elif action == "off":
                if self._system.situational:
                    self._system.situational._silent = True
                print("Autonomía DESACTIVADA")
            else:
                silent = getattr(self._system.situational, '_silent', False) if self._system.situational else True
                print(f"Autonomía: {'OFF' if silent else 'ON'}" + (" (sin coordinador)" if not self._system.situational else ""))

        elif cmd_name == "listen":
            await self._listen_once()

        elif cmd_name == "stt":
            await self._handle_stt_command(args)

        elif cmd_name == "vision":
            await self._handle_vision_command(args)

        elif cmd_name == "profile":
            if args:
                new_profile_str = args[0].upper()
                try:
                    self._profile = SystemProfile[new_profile_str]
                    print(f"Perfil cambiado a {self._profile.name} (requiere reinicio).")
                except KeyError:
                    print(f"Perfil no válido: {new_profile_str}")
            else:
                print(f"Perfil actual: {self._profile.name}")

        elif cmd_name == "intel":
            if args:
                self._intelligence_type = args[0].lower()
                print(f"Inteligencia cambiada a {self._intelligence_type} (requiere reinicio).")
            else:
                print(f"Inteligencia actual: {self._intelligence_type}")

        elif cmd_name == "quit":
            self._running = False

        else:
            print(f"Comando desconocido: /{cmd_name}")

    async def _handle_vision_command(self, args: list[str]) -> None:
        action = args[0].lower() if args else "status"
        if action == "on":
            await self._start_vision()
        elif action == "off":
            await self._stop_vision()
        else:
            status = "ACTIVA" if self._vision_loop is not None else "INACTIVA"
            print(f"Visión: {status}")

    async def _start_vision(self) -> None:
        assert self._system is not None
        if self._vision_loop is not None:
            print("Visión ya está activa.")
            return

        from sirah.autonomy.person_tracker import PersonTracker
        from sirah.autonomy.vision_loop import VisionLoop

        tracker = PersonTracker()
        self._vision_loop = VisionLoop(
            orchestrator=self._system.orchestrator,
            person_tracker=tracker,
            camera_device=0,
            analyze_interval=1.0,
            idle_min=12.0,
            idle_max=30.0,
            silent_after_user=8.0,
            silent=False,
        )
        await self._vision_loop.start()
        print("Visión ACTIVADA. Párate frente a la cámara. /vision off para detener.")

    async def _stop_vision(self) -> None:
        if self._vision_loop is None:
            print("Visión no está activa.")
            return
        await self._vision_loop.stop()
        self._vision_loop = None
        print("Visión DESACTIVADA.")

    async def _listen_once(self) -> None:
        assert self._system is not None
        try:
            from sirah.voice.mic_capture import MicCapture
        except ImportError:
            print("MicCapture no disponible (arecord no instalado).")
            return

        mic = MicCapture()
        print("Escuchando... (habla ahora, 5 segundos)")
        await mic.start()
        try:
            audio = await mic.record(duration_s=5.0)
        finally:
            await mic.stop()

        if len(audio) < 1000:
            print("No se detectó voz.")
            return

        print("Transcribiendo con Whisper tiny...")
        text = await self._transcribe(audio)

        if not text.strip():
            print("No se entendió lo que dijiste.")
            return

        print(f"\n[Dijiste]: {text}")

        if self._vision_loop is not None:
            self._vision_loop.mark_user_spoke()

        result = await self._system.orchestrator.handle_text(text)

        print(f"SIRAH: {result.message.content}")

        if self._system.speech_output is not None:
            await self._system.orchestrator.say(result.message.content)

    async def _transcribe(self, audio_wav: bytes) -> str:
        try:
            from sirah.voice.stt_whisper import WhisperSTT

            stt = WhisperSTT(model_size="tiny", language="es")
            await stt.start()
            try:
                result = await stt.transcribe(audio_wav)
                return result.text
            finally:
                await stt.stop()
        except Exception as exc:
            print(f"Error de transcripción: {exc}")
            return ""

    async def _handle_stt_command(self, args: list[str]) -> None:
        action = args[0].lower() if args else "status"
        if action == "on":
            if self._stt_active:
                print("STT ya está activo.")
                return
            self._stt_active = True
            self._stt_task = asyncio.create_task(self._stt_loop())
            print("STT continuo ACTIVADO. Habla cuando quieras. /stt off para detener.")
        elif action == "off":
            self._stt_active = False
            if self._stt_task:
                self._stt_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._stt_task
                self._stt_task = None
            print("STT DESACTIVADO.")
        else:
            print(f"STT: {'ACTIVO' if self._stt_active else 'INACTIVO'}")

    async def _stt_loop(self) -> None:
        assert self._system is not None
        from sirah.voice.mic_capture import MicCapture

        mic = MicCapture()
        await mic.start()
        try:
            while self._stt_active:
                audio = await mic.record(duration_s=3.0)
                if len(audio) < 1000:
                    await asyncio.sleep(0.5)
                    continue
                text = await self._transcribe(audio)
                if text.strip():
                    print(f"\r[Dijiste]: {text}")
                    if self._vision_loop is not None:
                        self._vision_loop.mark_user_spoke()
                    result = await self._system.orchestrator.handle_text(text)
                    print(f"\rSIRAH: {result.message.content}\nTú > ", end="", flush=True)
                    if self._system.speech_output is not None:
                        await self._system.orchestrator.say(result.message.content)
                await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            pass
        finally:
            await mic.stop()

    async def _camera_preview(self, duration: float = 5.0) -> None:
        import cv2

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("No se pudo abrir la cámara.")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        t_end = monotonic() + duration
        while monotonic() < t_end:
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            cv2.imshow("SIRAH Camera Preview (q para cerrar)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            await asyncio.sleep(0.03)

        cap.release()
        cv2.destroyAllWindows()

    async def _detect_faces(self) -> None:
        assert self._system is not None
        print("Detectando rostros...")
        frame = await self._system.orchestrator.perceive()
        if frame.faces:
            for i, face in enumerate(frame.faces):
                x, y, w, h = face.bbox
                print(
                    f"  Rostro {i+1}: "
                    f"({x:.2f}, {y:.2f}) [{w:.2f}x{h:.2f}] "
                    f"conf={face.confidence:.2f}"
                )
        else:
            print("  No se detectaron rostros (simulado).")


async def main() -> None:
    _load_dotenv()
    profile = SystemProfile.DEV_LAPTOP
    intel = "laboratory"
    tts = "fake"
    piper_voice = "es_ES-sharvard-medium"
    enable_vision = False

    for arg in sys.argv[1:]:
        if arg.startswith("--profile="):
            name = arg.split("=", 1)[1].upper()
            try:
                profile = SystemProfile[name]
            except KeyError:
                print(f"Perfil no válido: {name}")
                return
        elif arg.startswith("--intel="):
            intel = arg.split("=", 1)[1]
        elif arg == "--groq":
            intel = "groq"
        elif arg.startswith("--tts="):
            tts = arg.split("=", 1)[1]
        elif arg.startswith("--voice="):
            piper_voice = arg.split("=", 1)[1]
        elif arg == "--vision":
            enable_vision = True
        elif arg == "--help" or arg == "-h":
            print("sirah-console [--profile=DEV_LAPTOP|DEV_DISTRIBUTED] [--intel=fake|laboratory|scripted|groq] [--groq] [--tts=fake|piper|gtts] [--voice=name] [--vision]")
            return

    console = LaboratoryConsole(profile=profile, intelligence_type=intel, tts=tts, piper_voice=piper_voice, enable_vision=enable_vision)
    await console.run()


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
