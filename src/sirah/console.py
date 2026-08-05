"""Interactive Laboratory Console for SIRAH.

Text-based conversational interface. Optional webcam preview with face overlay.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from time import monotonic
from typing import Any

from sirah.factory import build_system, SystemProfile, SystemAssembly

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
    ) -> None:
        self._profile = profile
        self._intelligence_type = intelligence_type
        self._tts = tts
        self._piper_voice = piper_voice
        self._system: SystemAssembly | None = None
        self._running = False
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
        await self._system.orchestrator.start()
        await self._system.situational.start() if self._system.situational else None

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
        print("Detectando rostros...")
        frame = await self._system.orchestrator.perceive()  # type: ignore[union-attr]
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
    profile = SystemProfile.DEV_LAPTOP
    intel = "laboratory"
    tts = "fake"
    piper_voice = "es_ES-mls_9972-low"

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
        elif arg == "--help" or arg == "-h":
            print("sirah-console [--profile=DEV_LAPTOP|DEV_DISTRIBUTED] [--intel=fake|laboratory|scripted|groq] [--groq] [--tts=fake|piper|gtts] [--voice=es_ES-mls_9972-low]")
            return

    console = LaboratoryConsole(profile=profile, intelligence_type=intel, tts=tts, piper_voice=piper_voice)
    await console.run()


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
