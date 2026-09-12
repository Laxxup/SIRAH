#!/usr/bin/env python3
"""Measure Piper load and streaming synthesis latency for one utterance."""

import argparse
import json
import os
import time
import wave

from piper import PiperVoice


def memory_mb() -> tuple[float, float]:
    values = {}
    with open("/proc/self/status", encoding="ascii") as status:
        for line in status:
            if line.startswith(("VmRSS:", "VmHWM:")):
                values[line.split(":", 1)[0]] = float(line.split()[1]) / 1024
    return values.get("VmRSS", 0.0), values.get("VmHWM", 0.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--text",
        default="Hola. Esta es una prueba de síntesis de voz local para medir latencia y calidad.",
    )
    args = parser.parse_args()

    rss_before, _ = memory_mb()
    cpu_before = time.process_time()
    load_started = time.perf_counter()
    voice = PiperVoice.load(args.model)
    load_elapsed = time.perf_counter() - load_started
    cpu_after_load = time.process_time() - cpu_before
    rss_after, _ = memory_mb()

    chunks = []
    first_pcm = None
    synthesis_started = time.perf_counter()
    for chunk in voice.synthesize(args.text):
        if first_pcm is None:
            first_pcm = time.perf_counter() - synthesis_started
        chunks.append(chunk.audio_int16_bytes)
    total_elapsed = time.perf_counter() - synthesis_started
    cpu_synthesis = time.process_time() - cpu_before - cpu_after_load
    cpu_total = time.process_time() - cpu_before
    rss_peak, hwm = memory_mb()
    pcm = b"".join(chunks)
    duration = len(pcm) / (voice.config.sample_rate * 2 * 1)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with wave.open(args.output, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(voice.config.sample_rate)
        output.writeframes(pcm)

    result = {
        "model": args.model,
        "sample_rate": voice.config.sample_rate,
        "audio_seconds": round(duration, 3),
        "model_load_ms": round(load_elapsed * 1000, 1),
        "first_pcm_ms": round((first_pcm or total_elapsed) * 1000, 1),
        "total_synthesis_ms": round(total_elapsed * 1000, 1),
        "realtime_factor": round(total_elapsed / duration, 3) if duration else None,
        "cpu_synthesis_ms": round(cpu_synthesis * 1000, 1),
        "cpu_process_ms": round(cpu_total * 1000, 1),
        "rss_before_mb": round(rss_before, 1),
        "rss_after_load_mb": round(rss_after, 1),
        "rss_current_mb": round(rss_peak, 1),
        "rss_peak_mb": round(hwm, 1),
        "output": args.output,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
