"""Aggregate SIRAH `--lab` output into latency percentiles.

Experimental laboratory tooling for the M2 conversation-performance baseline.
Not part of the stable runtime. Reads `sirah-conversation listen --lab` output
from files or stdin and prints per-stage p50/p95/p99/min/max plus turn counts
and an estimated repair frequency.

Usage:
    python laboratory/latency_aggregate.py < logfile.txt
    python laboratory/latency_aggregate.py logfile1.log logfile2.log
    uv run sirah-conversation listen --live ... --lab | python laboratory/latency_aggregate.py

Recognized `--lab` output (src/sirah/conversation/timing.py + the CLI):

    [HH:MM:SS.mmm] Fin de voz detectado
    [HH:MM:SS.mmm] STT Groq: iniciando | etapa 0 ms | turno 1 ms
    [HH:MM:SS.mmm] STT Groq: listo | etapa 212 ms | turno 213 ms
    [HH:MM:SS.mmm] Ollama: respuesta lista | etapa 1380 ms | turno 1593 ms
    [HH:MM:SS.mmm] TTS: primer PCM listo | etapa 311 ms | turno 1904 ms
    [HH:MM:SS.mmm] Altavoz: iniciando | etapa 0 ms | turno 1904 ms
    [HH:MM:SS.mmm] Altavoz: reproducción terminada | etapa 2310 ms | turno 4214 ms
    estado: escuchando | procesando | hablando | interrumpido | recuperandose
    diagnóstico: propuesta descartada: <Exc>
    error de sesion: <msg>
    captura: sin descartes; cola max 2/8 | 3 frames descartados; cola max 8/8

`turno` is cumulative ms since `Fin de voz detectado`, so end-to-end spans are
turn_ms deltas; per-stage `etapa` values are adjacent deltas and are kept for
reference only. The repair estimate is derived (no marker exists for the
`core.py` double-proposal path): a turn whose LLM span is >= 1.5x the median is
counted as a suspected repair.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_MARKER = re.compile(
    r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\] (.+?)(?: \| etapa (\d+) ms \| turno (\d+) ms)?$"
)

_START_LABEL = "Fin de voz detectado"
_LLM_START = "Ollama: iniciando"
_LLM_READY = "Ollama: respuesta lista"
_TTS_START = "TTS: iniciando"
_TTS_FIRST = "TTS: primer PCM listo"
_PLAYER_START = "Altavoz: iniciando"
_PLAYER_END = "Altavoz: reproducción terminada"
_SILENT = "Respuesta: silenciosa"

_STATE_LABELS = {"escuchando", "procesando", "hablando", "interrumpido", "recuperandose"}


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, round(q * (len(values) - 1))))
    return values[index]


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f}"


def _summary(values: list[float]) -> dict[str, object]:
    values = sorted(values)
    if not values:
        return {"n": 0, "p50": None, "p95": None, "p99": None, "min": None, "max": None}
    return {
        "n": len(values),
        "p50": _fmt(_pct(values, 0.50)),
        "p95": _fmt(_pct(values, 0.95)),
        "p99": _fmt(_pct(values, 0.99)),
        "min": _fmt(values[0]),
        "max": _fmt(values[-1]),
    }


class SessionParser:
    """Group `--lab` markers into turns and collect per-stage statistics."""

    def __init__(self) -> None:
        self.turns: list[dict[str, tuple[float, float]]] = []
        self._current: dict[str, tuple[float, float]] = {}
        self.state_counts: dict[str, int] = defaultdict(int)
        self.diagnosed = 0
        self.errors = 0
        self.silent = 0
        self.provider: str | None = None
        self.capture_reports: list[str] = []

    def feed(self, line: str) -> None:
        stripped = line.strip()
        if not stripped:
            return
        match = _MARKER.match(stripped)
        if match:
            label = match.group(1)
            stage = float(match.group(2) or 0.0)
            turn_ms = float(match.group(3) or 0.0)
            if label == _START_LABEL:
                self._close_turn()
                self._current = {}
            self._current[label] = (stage, turn_ms)
            if (
                self.provider is None
                and label.startswith("STT ")
                and label.endswith(": iniciando")
            ):
                self.provider = label[4 : label.index(":")]
            return
        if stripped in _STATE_LABELS:
            self.state_counts[stripped] += 1
            return
        if stripped.startswith("diagnóstico:"):
            self.diagnosed += 1
            return
        if stripped.startswith("error de sesion:"):
            self.errors += 1
            return
        if stripped == _SILENT:
            self.silent += 1
            return
        if stripped.startswith("captura:"):
            self.capture_reports.append(stripped)

    def _close_turn(self) -> None:
        if self._current:
            self.turns.append(dict(self._current))
            self._current = {}

    def finalize(self) -> None:
        self._close_turn()

    def span(self, a: str, b: str) -> list[float]:
        spans = []
        for turn in self.turns:
            if a in turn and b in turn and turn[b][1] >= turn[a][1]:
                spans.append(turn[b][1] - turn[a][1])
        return spans


def _stt_labels(parser: SessionParser) -> tuple[str | None, str | None]:
    start = ready = None
    for turn in parser.turns:
        for label in turn:
            if label.startswith("STT ") and label.endswith(": iniciando"):
                start = label
            elif label.startswith("STT ") and label.endswith(": listo"):
                ready = label
    return start, ready


def main(argv: list[str]) -> int:
    sources = [arg for arg in argv if not arg.startswith("--")] or ["-"]
    parser = SessionParser()
    for source in sources:
        if source == "-":
            for line in sys.stdin:
                parser.feed(line)
        else:
            for line in Path(source).read_text(encoding="utf-8").splitlines():
                parser.feed(line)
    parser.finalize()

    stt_start, stt_ready = _stt_labels(parser)
    assert stt_start is not None and stt_ready is not None, (
        "no STT markers found; is this sirah-conversation listen --lab output?"
    )

    rows = [
        ("STT (inicio->listo)", parser.span(stt_start, stt_ready)),
        ("LLM (inicio->lista)", parser.span(_LLM_START, _LLM_READY)),
        ("TTS (inicio->primer)", parser.span(_TTS_START, _TTS_FIRST)),
        ("endpoint->STT inicio", parser.span(_START_LABEL, stt_start)),
        ("fin voz->altavoz (E2E)", parser.span(_START_LABEL, _PLAYER_START)),
        ("turno completo", parser.span(_START_LABEL, _PLAYER_END)),
    ]

    llm_values = [v for v in parser.span(_LLM_START, _LLM_READY) if v >= 0]
    median_llm = statistics.median(llm_values) if llm_values else None
    repair_estimate = (
        sum(1 for v in llm_values if median_llm and v >= 1.5 * median_llm)
        if median_llm
        else 0
    )

    print("SIRAH --lab latency aggregation")
    print("=" * 58)
    print(f"provider STT         : {parser.provider or 'unknown'}")
    print(f"turns parsed         : {len(parser.turns)}")
    print(f"  spoke              : {sum(1 for t in parser.turns if _PLAYER_START in t)}")
    print(f"  silent responses   : {parser.silent}")
    print(f"  diagnosed rejections: {parser.diagnosed}")
    print(f"  session errors     : {parser.errors}")
    print(f"  est. repairs (LLM>=1.5x median): {repair_estimate}")
    print(f"states               : {dict(parser.state_counts) or 'none'}")
    print(f"capture              : {parser.capture_reports[-1] if parser.capture_reports else 'n/a'}")
    print("-" * 58)
    print(f"{'metric':<24}{'n':>4}{'p50':>8}{'p95':>8}{'p99':>8}{'min':>7}{'max':>8}")
    print("-" * 58)
    for label, values in rows:
        s = _summary(values)
        print(
            f"{label:<24}{s['n']:>4}"
            f"{s['p50']!s:>8}{s['p95']!s:>8}{s['p99']!s:>8}"
            f"{s['min']!s:>7}{s['max']!s:>8}"
        )
    if "--json" in argv:
        payload = {"rows": [{"metric": m, **_summary(v)} for m, v in rows], "repair_estimate": repair_estimate}
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))