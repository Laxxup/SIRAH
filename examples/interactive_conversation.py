"""SIRAH Laboratory Console: demostración textual, no interfaz definitiva."""

from __future__ import annotations

import argparse
import os
import sys
from typing import TextIO

from sirah import (
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="interactive_conversation",
        description="SIRAH Laboratory Console (demostración textual).",
    )
    parser.add_argument("--provider", choices=("fake", "gemini"), default="fake")
    parser.add_argument("--enable-greet", action="store_true")
    parser.add_argument("--session-id", default="laboratory")
    return parser


def build_components(*, provider: str, enable_greet: bool) -> ComponentRegistry:
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
            ("output.speaker", ComponentKind.OUTPUT, "Altavoz no configurado."),
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


def _local_command(
    command: str,
    *,
    system: PresentSystem,
    session_id: str,
    output: TextIO,
) -> bool:
    if command == "/ayuda":
        print(
            "Comandos: /ayuda /estado /componentes /capacidades /contexto "
            "/eventos /limpiar /salir",
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
    system = PresentSystem(
        components=build_components(
            provider=provider_name, enable_greet=args.enable_greet
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
    print("SIRAH Laboratory Console — escribe /ayuda para comenzar.", file=output_stream)
    try:
        for raw_line in input_stream:
            message = raw_line.strip()
            if not message:
                continue
            if message.startswith("/"):
                if _local_command(
                    message,
                    system=system,
                    session_id=args.session_id,
                    output=output_stream,
                ):
                    break
                continue
            try:
                result = orchestrator.handle(args.session_id, message)
            except IntelligenceError as error:
                print(f"Error seguro: {type(error).__name__}.", file=output_stream)
                continue
            system.record_result(result)
            _print_result(result, system, args.session_id, output_stream)
    except KeyboardInterrupt:
        print("\nSIRAH Laboratory Console finalizada.", file=output_stream)
    finally:
        robot.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
