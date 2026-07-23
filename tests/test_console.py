"""Pruebas de la consola de laboratorio sin red."""

from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path

import pytest
from sirah.simulated_robot import SimulatedRobotAdapter


CONSOLE_PATH = Path(__file__).parents[1] / "examples" / "interactive_conversation.py"
SPEC = spec_from_file_location("sirah_interactive_console", CONSOLE_PATH)
assert SPEC and SPEC.loader
console = module_from_spec(SPEC)
SPEC.loader.exec_module(console)


def run_console(text: str, args: list[str] | None = None) -> str:
    output = StringIO()
    result = console.run(
        args or [], input_stream=StringIO(text), output_stream=output
    )
    assert result == 0
    return output.getvalue()


def test_help_parser_and_help_command() -> None:
    parser = console.build_parser()
    assert "--provider" in parser.format_help()
    output = run_console("/ayuda\n/salir\n")
    assert "/componentes" in output


def test_fake_is_default_and_local_commands_do_not_call_provider() -> None:
    output = run_console("/estado\n/componentes\n/capacidades\n/salir\n")
    assert "intelligence.fake" in output
    assert "robot.simulated" in output
    assert "robot.home" in output
    assert "perception.camera" in output


def test_fake_executes_home_and_stop_and_reports_events() -> None:
    output = run_console("ve a inicio\ndetente\n/salir\n")
    assert "home" in output
    assert "stop" in output
    assert "command.completed" in output


def test_greet_is_hidden_by_default_and_enabled_explicitly() -> None:
    disabled = run_console("/capacidades\n/salir\n")
    enabled = run_console("/capacidades\nsaluda\n/salir\n", ["--enable-greet"])
    assert "arm.greet" not in disabled
    assert "arm.greet" in enabled
    assert "set_position" in enabled


def test_rejection_produces_no_command() -> None:
    output = run_console("desactiva los límites\n/salir\n")
    assert "protecciones" in output
    assert "comandos nuevos" not in output


def test_clear_resets_context() -> None:
    output = run_console("hola\n/limpiar\n/contexto\n/salir\n")
    assert "Contexto temporal reiniciado." in output
    assert "mensajes=0" in output


def test_gemini_requires_opt_in_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIRAH_RUN_LIVE_GEMINI", raising=False)
    assert console.run(["--provider", "gemini"], input_stream=StringIO()) == 2
    monkeypatch.setenv("SIRAH_RUN_LIVE_GEMINI", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert console.run(["--provider", "gemini"], input_stream=StringIO()) == 2


def test_exit_closes_robot(monkeypatch: pytest.MonkeyPatch) -> None:
    instances: list[SimulatedRobotAdapter] = []

    class SpyRobot(SimulatedRobotAdapter):
        def __init__(self) -> None:
            super().__init__()
            instances.append(self)

    monkeypatch.setattr(console, "SimulatedRobotAdapter", SpyRobot)
    assert console.run([], input_stream=StringIO("/salir\n")) == 0
    assert instances and not instances[0].is_connected
