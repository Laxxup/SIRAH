from __future__ import annotations

from datetime import UTC, datetime

from sirah.conversation.timing import TurnTiming


def test_turn_timing_prints_wall_clock_stage_and_elapsed_durations():
    lines: list[str] = []
    monotonic_values = iter((10.0, 10.625, 12.0))
    wall_clock_values = iter(
        (
            datetime(2026, 8, 12, 12, 34, 56, 120_000, tzinfo=UTC),
            datetime(2026, 8, 12, 12, 34, 56, 745_000, tzinfo=UTC),
            datetime(2026, 8, 12, 12, 34, 57, 120_000, tzinfo=UTC),
        )
    )
    timing = TurnTiming(
        write=lines.append,
        monotonic_clock=lambda: next(monotonic_values),
        wall_clock=lambda: next(wall_clock_values),
    )

    timing.mark("Fin de voz detectado")
    timing.mark("STT Groq: listo")
    timing.mark("Respuesta: lista")

    assert lines == [
        "[12:34:56.120] Fin de voz detectado",
        "[12:34:56.745] STT Groq: listo | etapa 625 ms | turno 625 ms",
        "[12:34:57.120] Respuesta: lista | etapa 1375 ms | turno 2000 ms",
    ]


def test_turn_timing_reset_starts_a_new_turn():
    lines: list[str] = []
    monotonic_values = iter((10.0, 11.0, 20.0))
    wall_clock_values = iter(
        (
            datetime(2026, 8, 12, 12, 34, 56, tzinfo=UTC),
            datetime(2026, 8, 12, 12, 34, 57, tzinfo=UTC),
            datetime(2026, 8, 12, 12, 35, 6, tzinfo=UTC),
        )
    )
    timing = TurnTiming(
        write=lines.append,
        monotonic_clock=lambda: next(monotonic_values),
        wall_clock=lambda: next(wall_clock_values),
    )

    timing.mark("primer turno")
    timing.mark("primer turno listo")
    timing.reset()
    timing.mark("segundo turno")

    assert lines[-1] == "[12:35:06.000] segundo turno"
