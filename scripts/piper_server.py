#!/usr/bin/env python3
"""Persistent Piper bridge with length-delimited signed 16-bit PCM output."""

import argparse
import struct
import sys

from piper import PiperVoice


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    voice = PiperVoice.load(args.model)
    for line in sys.stdin:
        text = line.rstrip("\r\n")
        if not text:
            continue
        for chunk in voice.synthesize(text):
            data = chunk.audio_int16_bytes
            sys.stdout.buffer.write(struct.pack(">I", len(data)))
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        sys.stdout.buffer.write(struct.pack(">I", 0))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
