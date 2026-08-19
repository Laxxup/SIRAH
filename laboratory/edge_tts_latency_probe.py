"""Compare Edge TTS first-audio latency: fresh Communicate vs shared aiohttp connector.

Experimental laboratory tooling (M2 Phase 3, Priority 2). The stable runtime
creates a fresh ``edge_tts.Communicate`` per call
(``src/sirah/audio/edge_tts.py``), so each synthesis pays a new WebSocket
connect + TLS handshake. This probe measures time-to-first-audio for that
baseline against a variant that reuses one aiohttp connector.

Usage:

    uv run python laboratory/edge_tts_latency_probe.py --samples 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import edge_tts


async def _first_audio_ms(communicate: edge_tts.Communicate) -> float:
    started = time.monotonic()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio" and isinstance(chunk.get("data"), bytes):
            return (time.monotonic() - started) * 1000
    raise RuntimeError("no audio chunks received")


async def _fresh(text: str, voice: str) -> float:
    return await _first_audio_ms(edge_tts.Communicate(text, voice))


async def _shared_connector(text: str, voice: str, connector) -> float:
    communicate = edge_tts.Communicate(text, voice, connector=connector)
    return await _first_audio_ms(communicate)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--text", default="Hola, soy SIRAH.")
    parser.add_argument("--voice", default="es-MX-DaliaNeural")
    args = parser.parse_args()

    import aiohttp

    fresh: list[float] = []
    shared: list[float] = []
    connector = aiohttp.TCPConnector(limit=4)
    try:
        for i in range(args.samples):
            fresh.append(await _fresh(args.text, args.voice))
            print(f"fresh {i + 1}: {fresh[-1]:.0f} ms", flush=True)
        for i in range(args.samples):
            shared.append(await _shared_connector(args.text, args.voice, connector))
            print(f"connector {i + 1}: {shared[-1]:.0f} ms", flush=True)
    finally:
        await connector.close()

    def pct(values: list[float], q: float) -> float:
        values = sorted(values)
        return values[max(0, min(len(values) - 1, round(q * (len(values) - 1))))]

    print(
        json.dumps(
            {
                "fresh": {
                    "n": len(fresh),
                    "p50": round(pct(fresh, 0.5)),
                    "p95": round(pct(fresh, 0.95)),
                },
                "shared_connector": {
                    "n": len(shared),
                    "p50": round(pct(shared, 0.5)),
                    "p95": round(pct(shared, 0.95)),
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
