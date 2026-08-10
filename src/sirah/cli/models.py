"""Explicit installer commands for optional SIRAH perception models."""

from __future__ import annotations

import argparse
from pathlib import Path

from sirah.perception.models import install_yunet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sirah-models")
    subparsers = parser.add_subparsers(dest="model", required=True)
    yunet = subparsers.add_parser("yunet", help="download and verify YuNet")
    yunet.add_argument("--destination", type=Path, default=Path("models/yunet"))
    args = parser.parse_args(argv)
    print(install_yunet(args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
