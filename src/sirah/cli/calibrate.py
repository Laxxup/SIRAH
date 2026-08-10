"""`sirah-calibrate` CLI (Stage 7: minimal; Stage 12 expands).

Stage 7 scope: `--validate` checks the actuator mirror YAML against the
firmware calibration.h authority and reports discrepancies. Interactive
calibration flows (sweeps, recordings, apply-to-header) arrive in Stage 12.
"""

from __future__ import annotations

import argparse
import sys

from sirah.config import consistency


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sirah-calibrate",
        description="SIRAH v0.3.0 calibration tooling (Milestone 1; "
        "subsistema de ojos de SIRAH — Sistema Inteligente Robótico de "
        "Asistencia Humana).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="YAML↔calibration.h mirror check")
    validate.add_argument(
        "--actuators",
        default=None,
        help="actuator mirror YAML (default: config/actuators.yaml)",
    )
    validate.add_argument(
        "--header",
        default=None,
        help="firmware calibration.h (default: firmware/sirah-eyes/config/calibration.h)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return _cmd_validate(args)
    return 2  # pragma: no cover - argparse blocks unknown subcommands


def _cmd_validate(args: argparse.Namespace) -> int:
    problems = consistency.verify_mirror_files(args.actuators, args.header)
    if not problems:
        print("sirah-calibrate: OK — actuators.yaml mirrors calibration.h")
        return 0
    print("sirah-calibrate: MISMATCH (firmware is the authority):", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())