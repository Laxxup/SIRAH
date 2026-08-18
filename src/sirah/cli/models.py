"""Explicit installer commands for optional SIRAH perception models."""

from __future__ import annotations

import argparse
from pathlib import Path

from sirah.perception.models import install_gesture, install_person, install_yunet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sirah-models")
    subparsers = parser.add_subparsers(dest="model", required=True)
    yunet = subparsers.add_parser("yunet", help="download and verify YuNet")
    yunet.add_argument("--destination", type=Path, default=Path("models/yunet"))
    gesture = subparsers.add_parser("gesture", help="download and verify MediaPipe gesture model")
    gesture.add_argument("--destination", type=Path, default=Path("models/gesture"))
    person = subparsers.add_parser("person", help="download and verify MediaPipe person model (M6)")
    person.add_argument("--destination", type=Path, default=Path("models/person"))
    args = parser.parse_args(argv)
    if args.model == "gesture":
        print(install_gesture(args.destination))
        return 0
    if args.model == "person":
        print(install_person(args.destination))
        return 0
    print(install_yunet(args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
