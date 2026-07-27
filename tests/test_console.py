"""Pruebas de la consola de laboratorio sin red."""

from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
import os
from pathlib import Path
import threading

import pytest
from sirah.simulated_robot import SimulatedRobotAdapter
from sirah.speech_input import SpeechRecognitionEvent, SpeechRecognitionEventKind


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
    assert "--speech-provider" in parser.format_help()
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


def test_fake_voice_status_and_manual_completion() -> None:
    output = run_console(
        "/presencia person:test\n/voz-estado\n/voz-fin\n/estado\n/salir\n"
    )
    assert "output.speech.fake" not in output
    assert "estado=playing" in output
    assert "TTS simulado finalizado." in output
    assert "TTS activo: False" in output


def test_piper_degraded_keeps_text_console_running() -> None:
    output = run_console(
        "/componentes\n/voz-estado\n/voz-fin\nhola\n/salir\n",
        [
            "--speech-provider",
            "piper",
            "--piper-bin",
            "definitely-missing-piper",
            "--piper-model",
            "definitely-missing-model",
            "--audio-player",
            "definitely-missing-player",
        ],
    )
    assert "output.speech.piper: degraded" in output
    assert "disponible=False" in output
    assert "solo está disponible para el proveedor fake" in output
    assert "Puedo conversar por texto" in output


def test_posix_console_drains_stt_without_another_input_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = threading.Event()
    started = threading.Event()
    publish = threading.Event()
    delivered = threading.Event()

    class ControlledRuntime:
        available = True
        active = False
        state = type("State", (), {"value": "idle"})()

        def __init__(self, *args: object, **kwargs: object) -> None:
            self.operation_id = "stt-controlled"
            self.sent = False
            created.set()

        def start(self) -> str:
            self.active = True
            started.set()
            return self.operation_id

        def poll(self) -> SpeechRecognitionEvent | None:
            if publish.is_set() and not self.sent:
                self.sent = True
                self.active = False
                delivered.set()
                return SpeechRecognitionEvent(
                    self.operation_id,
                    SpeechRecognitionEventKind.FINAL,
                    text="hola",
                )
            return None

        def finalize(self, expected_operation_id: str | None = None) -> bool:
            return False

        def cancel(self, expected_operation_id: str | None = None) -> bool:
            return False

        def close(self) -> None:
            self.active = False

    monkeypatch.setattr(console, "SpeechInputRuntime", ControlledRuntime)
    read_fd, write_fd = os.pipe()
    input_stream = os.fdopen(read_fd, "r", encoding="utf-8")
    output = StringIO()
    result: list[int] = []
    thread = threading.Thread(
        target=lambda: result.append(
            console.run(
                ["--speech-input-provider", "fake"],
                input_stream=input_stream,
                output_stream=output,
            )
        )
    )
    thread.start()
    assert created.wait(1)
    os.write(write_fd, b"/escuchar\n")
    assert started.wait(1)
    publish.set()
    assert delivered.wait(1)
    os.close(write_fd)
    thread.join(1)
    assert not thread.is_alive()
    input_stream.close()
    assert result == [0]
    text = output.getvalue()
    assert text.count("Entrada terminal: final.") == 1
    assert text.count("Puedo conversar por texto") == 1


@pytest.mark.parametrize(
    "command",
    ["/escuchar", "/escuchar-finalizar", "/escuchar-cancelar", "/escucha-estado"],
)
def test_ptt_commands_degrade_with_provider_none(command: str) -> None:
    output = run_console(f"{command}\n/salir\n")
    assert "Traceback" not in output


def test_vosk_missing_model_degrades_to_text() -> None:
    output = run_console(
        "hola\n/salir\n", ["--speech-input-provider", "vosk"]
    )
    assert "Vosk sin modelo" in output
    assert "Puedo conversar por texto" in output


@pytest.mark.parametrize(
    "arguments",
    [
        ["--sample-rate", "0", "--vosk-model", "missing"],
        ["--sample-rate", "-1", "--vosk-model", "missing"],
        ["--sample-rate", "texto", "--vosk-model", "missing"],
        ["--arecord-bin", "", "--vosk-model", "missing"],
        ["--arecord-bin", "definitely-missing-arecord", "--vosk-model", "missing"],
        ["--audio-input-device", "", "--vosk-model", "missing"],
        ["--audio-input-device", "hw:0;other", "--vosk-model", "missing"],
        ["--vosk-model", "definitely/missing/model"],
    ],
)
def test_invalid_vosk_console_configuration_degrades_to_text(
    arguments: list[str],
) -> None:
    output = run_console(
        "hola\n/salir\n",
        ["--speech-input-provider", "vosk", *arguments],
    )
    assert "Configuración Vosk inválida; continúa el modo texto." in output
    assert "Puedo conversar por texto" in output
    assert "Traceback" not in output


def test_all_ptt_commands_with_fake_provider_close_orderly() -> None:
    output = run_console(
        "/escucha-estado\n/escuchar\n/escuchar-finalizar\n"
        "/escuchar-cancelar\n/escucha-estado\n/salir\n",
        ["--speech-input-provider", "fake"],
    )
    assert "Escucha iniciada:" in output
    assert "Finalización solicitada:" in output
    assert "Cancelación solicitada:" in output
    assert output.count("Entrada terminal:") <= 1
    assert "Traceback" not in output


def test_stringio_no_fileno_path_reads_terminal_line_without_newline() -> None:
    output = run_console("/escucha-estado", ["--speech-input-provider", "none"])
    assert "ENTRADA: proveedor=none." in output
    assert "Traceback" not in output


def test_console_source_has_no_sleep_or_busy_spin_contract() -> None:
    source = CONSOLE_PATH.read_text(encoding="utf-8")
    assert "time.sleep" not in source
    assert "sleep(" not in source
    assert "selector.select(self._timeout)" in source
