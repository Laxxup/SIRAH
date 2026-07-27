"""SIRAH Laboratory Console: demostración textual, no interfaz definitiva."""

from __future__ import annotations

import argparse
import selectors
import os
import sys
from typing import TextIO

from sirah import (
    AudioTurnCoordinator,
    CapabilityRunner,
    ConversationOrchestrator,
    SessionContextStore,
    create_default_catalog,
)
from sirah.demo import LaboratoryFakeIntelligence
from sirah.errors import IntelligenceError
from sirah.gemini import GeminiIntelligenceAdapter
from sirah.simulated_robot import SimulatedRobotAdapter
from sirah.system import (
    ComponentId,
    ComponentKind,
    ComponentRegistry,
    ComponentState,
    ComponentStatus,
    PresentSystem,
)
from sirah.situational import (
    SituationalCoordinator,
)
from sirah.simulation import FakeClock, FakeSpeechOutput, SimulatedPerception
from sirah.piper_speech import PiperSpeechConfig, PiperSpeechOutput
from sirah.arecord_capture import ArecordPcmCapture, ArecordPcmConfig
from sirah.guarded_speech import (
    FakeSpeechOutputLabControl,
    GuardedSpeechOutput,
    SpeechOutputLabControlPort,
)
from sirah.speech_fakes import FakePcmCapture, FakeSpeechRecognizer
from sirah.speech_input import (
    RecognitionUpdate,
    RecognitionUpdateKind,
    SpeechInputRuntime,
)
from sirah.speech_input_coordinator import SpeechInputCoordinator
from sirah.vosk_recognizer import VoskRecognizerConfig, VoskSpeechRecognizer
from sirah.situational_runtime import build_situational_runtime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="interactive_conversation",
        description="SIRAH Laboratory Console (demostración textual).",
    )
    parser.add_argument("--provider", choices=("fake", "gemini"), default="fake")
    parser.add_argument("--enable-greet", action="store_true")
    parser.add_argument("--session-id", default="laboratory")
    parser.add_argument("--speech-provider", choices=("fake", "piper"), default="fake")
    parser.add_argument("--piper-bin")
    parser.add_argument("--piper-model")
    parser.add_argument("--piper-config")
    parser.add_argument("--audio-player")
    parser.add_argument(
        "--speech-input-provider", choices=("none", "fake", "vosk"), default="none"
    )
    parser.add_argument("--vosk-model")
    parser.add_argument("--audio-input-device")
    parser.add_argument("--sample-rate", default="16000")
    parser.add_argument("--arecord-bin", default="arecord")
    return parser


def build_components(
    *,
    provider: str,
    enable_greet: bool,
    speech_provider: str = "fake",
    speech_available: bool = True,
    speech_reason: str | None = None,
) -> ComponentRegistry:
    components = [
        ComponentState(
            ComponentId(f"intelligence.{provider}"),
            ComponentKind.INTELLIGENCE,
            ComponentStatus.AVAILABLE,
            simulated=provider == "fake",
            description="Proveedor de texto activo.",
        ),
        ComponentState(
            ComponentId("context.session_memory"),
            ComponentKind.CONTEXT,
            ComponentStatus.AVAILABLE,
            simulated=True,
            description="Contexto temporal en memoria.",
        ),
        ComponentState(
            ComponentId("control.sirah_cortex"),
            ComponentKind.CONTROL,
            ComponentStatus.AVAILABLE,
            simulated=True,
            description="Validación y ejecución determinista de Cortex.",
        ),
        ComponentState(
            ComponentId("robot.simulated"),
            ComponentKind.ROBOT,
            ComponentStatus.SIMULATED,
            simulated=True,
            description="RobotPort local sin hardware.",
            capabilities=("robot.home", "robot.stop"),
        ),
        ComponentState(
            ComponentId(f"output.speech.{speech_provider}"),
            ComponentKind.OUTPUT,
            ComponentStatus.SIMULATED
            if speech_provider == "fake"
            else (
                ComponentStatus.AVAILABLE
                if speech_available
                else ComponentStatus.DEGRADED
            ),
            simulated=speech_provider == "fake",
            description=(
                "TTS fake determinista."
                if speech_provider == "fake"
                else "Piper CLI experimental; hardware de audio no validado."
            ),
            capabilities=("interaction.greet",),
            last_error=speech_reason,
        ),
    ]
    if enable_greet:
        components.append(
            ComponentState(
                ComponentId("body.right_arm"),
                ComponentKind.BODY,
                ComponentStatus.SIMULATED,
                simulated=True,
                description="Brazo derecho representado por Cortex.",
                capabilities=("arm.greet",),
            )
        )
    components.extend(
        ComponentState(
            ComponentId(identifier),
            kind,
            ComponentStatus.UNAVAILABLE,
            simulated=False,
            description=description,
        )
        for identifier, kind, description in (
            ("perception.camera", ComponentKind.PERCEPTION, "Cámara no configurada."),
            ("input.microphone", ComponentKind.INPUT, "Micrófono no configurado."),
            ("output.speaker", ComponentKind.OUTPUT, "Hardware de audio no validado."),
            ("memory.persistent", ComponentKind.MEMORY, "Memoria persistente no configurada."),
            ("robot.physical", ComponentKind.ROBOT, "Cuerpo físico no configurado."),
        )
    )
    return ComponentRegistry(components)


def _print_components(system: PresentSystem, output: TextIO) -> None:
    print("COMPONENTES", file=output)
    for component in system.components.all():
        simulation = "simulado" if component.simulated else "no simulado"
        print(
            f"- {component.identifier.value}: {component.status.value} ({simulation}) — "
            f"{component.description}",
            file=output,
        )


def _print_snapshot(system: PresentSystem, session_id: str, output: TextIO) -> None:
    snapshot = system.snapshot(session_id)
    print("ESTADO", file=output)
    print(f"- sesión: {snapshot.session_id}", file=output)
    print(f"- inteligencia: {snapshot.intelligence_provider}", file=output)
    print(f"- Cortex conectado: {snapshot.robot_connected}", file=output)
    print(f"- seguridad: {snapshot.safety_state}", file=output)
    print(f"- última capacidad: {snapshot.last_capability or 'ninguna'}", file=output)
    print(f"- último resultado: {snapshot.last_result or 'ninguno'}", file=output)
    print(f"- mensajes recientes: {snapshot.recent_message_count}", file=output)
    print(f"- comandos recientes: {list(snapshot.recent_commands)}", file=output)
    print(f"- errores seguros: {list(snapshot.safe_errors)}", file=output)
    print(f"- silencio: {snapshot.silent_mode}", file=output)
    print(f"- autonomía: {snapshot.autonomy_active}", file=output)
    print(f"- TTS activo: {snapshot.tts_active}", file=output)
    print(
        f"- razón de iniciativa: {snapshot.last_initiative_reason or 'ninguna'}",
        file=output,
    )


def _local_command(
    command: str,
    *,
    system: PresentSystem,
    coordinator: SituationalCoordinator,
    lab_control: SpeechOutputLabControlPort | None = None,
    speech_input: SpeechInputCoordinator | None = None,
    session_id: str,
    output: TextIO,
) -> bool:
    if command == "/ayuda":
        print(
            "Comandos: /ayuda /estado /componentes /capacidades /contexto "
            "/eventos /limpiar /voz-estado /voz-detener /voz-fin "
            "/escuchar /escuchar-finalizar /escuchar-cancelar /escucha-estado /salir",
            file=output,
        )
    elif command == "/estado":
        _print_snapshot(system, session_id, output)
    elif command == "/componentes":
        _print_components(system, output)
    elif command == "/capacidades":
        print("CAPACIDADES HABILITADAS", file=output)
        for capability in system.snapshot(session_id).enabled_capabilities:
            print(f"- {capability}", file=output)
    elif command == "/contexto":
        snapshot = system.snapshot(session_id)
        print(
            f"CONTEXTO: sesión={session_id}; mensajes={snapshot.recent_message_count}; "
            f"última capacidad={snapshot.last_capability or 'ninguna'}",
            file=output,
        )
    elif command == "/eventos":
        print("EVENTOS RECIENTES", file=output)
        for event in system.snapshot(session_id).recent_events or ("ninguno",):
            print(f"- {event}", file=output)
    elif command == "/limpiar":
        system.contexts.clear(session_id)
        print("Contexto temporal reiniciado.", file=output)
    elif command.startswith("/presencia"):
        parts = command.split()
        key = parts[1] if len(parts) > 1 else "presence:current"
        coordinator.inject_presence(present=True, presence_key=key)
        decision = coordinator.evaluate_and_act(presence_key=key)
        system.record_interaction_state(coordinator.memory)
        print(f"Presencia simulada: {key}; iniciativa={decision.action.value}; razón={decision.reason}", file=output)
    elif command == "/ausencia":
        coordinator.inject_presence(present=False)
        system.record_interaction_state(coordinator.memory)
        print("Ausencia simulada procesada.", file=output)
    elif command == "/evaluar":
        decision = coordinator.evaluate_and_act()
        system.record_interaction_state(coordinator.memory)
        print(f"Iniciativa={decision.action.value}; razón={decision.reason}", file=output)
    elif command.startswith("/silencio"):
        parts = command.split()
        active = len(parts) == 1 or parts[1].casefold() in {"on", "activar", "sí", "si"}
        coordinator.set_silent(active)
        system.record_interaction_state(coordinator.memory)
        print(f"Modo silencio: {'activo' if active else 'inactivo'}.", file=output)
    elif command.startswith("/autonomia"):
        parts = command.split()
        active = len(parts) == 1 or parts[1].casefold() in {"on", "activar", "sí", "si"}
        coordinator.set_autonomy(active)
        system.record_interaction_state(coordinator.memory)
        print(f"Autonomía: {'activa' if active else 'pausada'}.", file=output)
    elif command in {"/detener", "/stop"}:
        stop_result = coordinator.stop("stop", request_id=f"{session_id}:local-stop")
        system.record_interaction_state(coordinator.memory)
        print(
            f"Stop local: matched={stop_result.matched}; "
            f"tts_cancelled={stop_result.tts_cancelled}; "
            "robot_action=stop; "
            f"robot_ok={bool(stop_result.robot_result and stop_result.robot_result.succeeded)}",
            file=output,
        )
    elif command == "/voz-estado":
        print(
            f"VOZ: disponible={coordinator.speech.available}; "
            f"activo={coordinator.speech.active}; "
            f"estado={coordinator.speech.state.value}",
            file=output,
        )
    elif command == "/voz-detener":
        cancelled = coordinator.speech.stop()
        coordinator.sync_speech()
        system.record_interaction_state(coordinator.memory)
        print(f"Voz detenida: {cancelled}.", file=output)
    elif command == "/voz-fin":
        if lab_control is not None:
            lab_control.complete_active()
            coordinator.sync_speech()
            system.record_interaction_state(coordinator.memory)
            print("TTS simulado finalizado.", file=output)
        else:
            print("/voz-fin solo está disponible para el proveedor fake.", file=output)
    elif command == "/escuchar":
        if speech_input is None:
            print("Entrada de voz no configurada; texto disponible.", file=output)
        else:
            try:
                print(f"Escucha iniciada: {speech_input.start()}.", file=output)
            except Exception as error:
                print(f"Escucha rechazada: {type(error).__name__}.", file=output)
    elif command == "/escuchar-finalizar":
        accepted = speech_input is not None and speech_input.input.finalize()
        print(f"Finalización solicitada: {accepted}.", file=output)
    elif command == "/escuchar-cancelar":
        accepted = speech_input is not None and speech_input.input.cancel()
        print(f"Cancelación solicitada: {accepted}.", file=output)
    elif command == "/escucha-estado":
        if speech_input is None:
            print("ENTRADA: proveedor=none.", file=output)
        else:
            print(
                f"ENTRADA: disponible={speech_input.input.available}; "
                f"activo={speech_input.input.active}; "
                f"estado={speech_input.input.state.value}.",
                file=output,
            )
    elif command == "/salir":
        print("SIRAH Laboratory Console finalizada.", file=output)
        return True
    else:
        print("Comando local desconocido. Usa /ayuda.", file=output)
    return False


def _print_result(result: object, system: PresentSystem, session_id: str, output: TextIO) -> None:
    decision = getattr(result, "decision", None)
    mechanical = getattr(result, "mechanical_result", None)
    print("RESPUESTA", file=output)
    print(f"- texto: {getattr(result, 'response_text', '')}", file=output)
    print(
        f"- decisión: {decision.decision_type.value if decision else 'no disponible'}",
        file=output,
    )
    print(
        f"- capacidad propuesta: {getattr(result, 'requested_capability', None) or 'ninguna'}",
        file=output,
    )
    print(
        f"- autorizada/ejecutada: {getattr(result, 'capability_executed', False)}",
        file=output,
    )
    print(f"- error seguro: {getattr(result, 'safe_error', None) or 'ninguno'}", file=output)
    if mechanical is not None:
        print(
            f"- comandos nuevos: {[command.action for command in mechanical.delivered_commands]}",
            file=output,
        )
        print(
            f"- eventos relevantes: {[event.type.value for event in mechanical.events]}",
            file=output,
        )
    _print_snapshot(system, session_id, output)


def _drain_speech_input(
    speech_input: SpeechInputCoordinator | None,
    *,
    system: PresentSystem,
    session_id: str,
    output: TextIO,
) -> None:
    if speech_input is None:
        return
    while True:
        dispatch = speech_input.poll()
        if dispatch is None:
            return
        event = dispatch.event
        if event.kind.value == "partial":
            continue
        print(f"Entrada terminal: {event.kind.value}.", file=output)
        if dispatch.conversation is not None:
            system.record_result(dispatch.conversation)
            _print_result(dispatch.conversation, system, session_id, output)
        elif dispatch.stop is not None:
            print("Stop vocal local procesado.", file=output)


class _ConsoleInput:
    """Lectura seleccionable en POSIX y determinista para streams de pruebas."""

    def __init__(self, stream: TextIO, *, timeout_seconds: float = 0.05) -> None:
        self._stream = stream
        self._selector: selectors.BaseSelector | None = None
        try:
            descriptor = stream.fileno()
            selector = selectors.DefaultSelector()
            selector.register(descriptor, selectors.EVENT_READ)
            self._selector = selector
        except (AttributeError, OSError, TypeError, ValueError):
            if "selector" in locals():
                selector.close()
        self._timeout = timeout_seconds

    def read(self) -> tuple[bool, str | None]:
        if self._selector is not None and not self._selector.select(self._timeout):
            return False, None
        line = self._stream.readline()
        return True, line if line else None

    def close(self) -> None:
        if self._selector is not None:
            self._selector.close()


def run(
    argv: list[str] | None = None,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    if args.provider == "gemini":
        if os.environ.get("SIRAH_RUN_LIVE_GEMINI") != "1":
            print("Gemini requiere SIRAH_RUN_LIVE_GEMINI=1.", file=output_stream)
            return 2
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            print("Gemini requiere GEMINI_API_KEY o GOOGLE_API_KEY.", file=output_stream)
            return 2
        intelligence = GeminiIntelligenceAdapter(max_retries=1)
        provider_name = "gemini"
    else:
        intelligence = LaboratoryFakeIntelligence(enable_greet=args.enable_greet)
        provider_name = "fake"
    catalog = create_default_catalog(enable_greet=args.enable_greet)
    robot = SimulatedRobotAdapter()
    robot.connect()
    robot.read_events()
    contexts = SessionContextStore()
    turns = AudioTurnCoordinator()
    lab_control: SpeechOutputLabControlPort | None = None
    if args.speech_provider == "piper":
        from pathlib import Path

        concrete_speech = PiperSpeechOutput(
            PiperSpeechConfig.from_environment(
                piper_executable=args.piper_bin,
                model_path=Path(args.piper_model) if args.piper_model else None,
                config_path=Path(args.piper_config) if args.piper_config else None,
                player_argv=(args.audio_player,) if args.audio_player else None,
            )
        )
    else:
        concrete_speech = FakeSpeechOutput()
        lab_control = FakeSpeechOutputLabControl(concrete_speech.complete)
    speech = GuardedSpeechOutput(concrete_speech, turns)
    speech_runtime: SpeechInputRuntime | None = None
    if args.speech_input_provider == "fake":
        speech_runtime = SpeechInputRuntime(
            FakePcmCapture(),
            FakeSpeechRecognizer(
                final=RecognitionUpdate(RecognitionUpdateKind.NO_SPEECH)
            ),
            turns,
        )
    elif args.speech_input_provider == "vosk":
        if not args.vosk_model:
            print("Vosk sin modelo; continúa el modo texto.", file=output_stream)
        else:
            from pathlib import Path

            try:
                sample_rate = int(args.sample_rate)
                if not 8000 <= sample_rate <= 48000:
                    raise ValueError("sample_rate_out_of_range")
                capture = ArecordPcmCapture(
                    ArecordPcmConfig(
                        executable=args.arecord_bin,
                        device=args.audio_input_device,
                        sample_rate=sample_rate,
                    )
                )
                recognizer = VoskSpeechRecognizer(
                    VoskRecognizerConfig(Path(args.vosk_model), sample_rate)
                )
                if not capture.available or not recognizer.available:
                    capture.close()
                    recognizer.close()
                    raise ValueError("speech_input_unavailable")
                speech_runtime = SpeechInputRuntime(
                    capture,
                    recognizer,
                    turns,
                )
            except (OSError, ValueError):
                print(
                    "Configuración Vosk inválida; continúa el modo texto.",
                    file=output_stream,
                )
    system = PresentSystem(
        components=build_components(
            provider=provider_name,
            enable_greet=args.enable_greet,
            speech_provider=args.speech_provider,
            speech_available=speech.available,
            speech_reason=getattr(speech, "unavailable_reason", None),
        ),
        catalog=catalog,
        contexts=contexts,
        robot=robot,
        intelligence_provider=provider_name,
    )
    orchestrator = ConversationOrchestrator(
        intelligence=intelligence,
        catalog=catalog,
        runner=CapabilityRunner(catalog, robot),
        contexts=contexts,
    )
    runtime, inbox, _ = build_situational_runtime(robot=robot, at=0.0)
    coordinator = SituationalCoordinator(
        runtime=runtime,
        inbox=inbox,
        perception=SimulatedPerception(),
        speech=speech,
        runner=CapabilityRunner(catalog, robot),
        components=system.components,
        clock=FakeClock(0.0),
    )
    speech_input = (
        SpeechInputCoordinator(
            speech_runtime,
            stop_router=coordinator.stop_router,
            speech_output=speech,
            runner=coordinator.runner,
            conversation=orchestrator,
            session_id=args.session_id,
        )
        if speech_runtime is not None
        else None
    )
    system.record_interaction_state(coordinator.memory)
    print("SIRAH Laboratory Console — escribe /ayuda para comenzar.", file=output_stream)
    console_input = _ConsoleInput(input_stream)
    try:
        while True:
            _drain_speech_input(
                speech_input,
                system=system,
                session_id=args.session_id,
                output=output_stream,
            )
            coordinator.sync_speech()
            system.record_interaction_state(coordinator.memory)
            ready, raw_line = console_input.read()
            if not ready:
                continue
            if raw_line is None:
                _drain_speech_input(
                    speech_input,
                    system=system,
                    session_id=args.session_id,
                    output=output_stream,
                )
                break
            message = raw_line.strip()
            if not message:
                continue
            if message.startswith("/"):
                if _local_command(
                    message,
                    system=system,
                    coordinator=coordinator,
                    lab_control=lab_control,
                    speech_input=speech_input,
                    session_id=args.session_id,
                    output=output_stream,
                ):
                    break
                coordinator.sync_speech()
                _drain_speech_input(
                    speech_input,
                    system=system,
                    session_id=args.session_id,
                    output=output_stream,
                )
                system.record_interaction_state(coordinator.memory)
                continue
            if coordinator.stop_router.matches(message):
                _local_command(
                    "/detener",
                    system=system,
                    coordinator=coordinator,
                    session_id=args.session_id,
                    output=output_stream,
                )
                continue
            try:
                result = orchestrator.handle(args.session_id, message)
            except IntelligenceError as error:
                print(f"Error seguro: {type(error).__name__}.", file=output_stream)
                continue
            system.record_result(result)
            _print_result(result, system, args.session_id, output_stream)
            coordinator.sync_speech()
            system.record_interaction_state(coordinator.memory)
    except KeyboardInterrupt:
        print("\nSIRAH Laboratory Console finalizada.", file=output_stream)
    finally:
        console_input.close()
        if speech_runtime is not None:
            speech_runtime.close()
        speech.close()
        robot.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
