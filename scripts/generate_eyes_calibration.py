#!/usr/bin/env python3
"""Genera firmware/sirah/calibration.h desde config/eyes-calibration.toml.

Determinista: misma entrada -> mismos bytes. El ESP32 no parsea TOML,
solo incluye el header generado (vive junto al sketch para arduino-cli).
Uso: python3 scripts/generate_eyes_calibration.py [--check]
"""
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOML_PATH = ROOT / "config" / "eyes-calibration.toml"
HEADER_PATH = ROOT / "firmware" / "sirah" / "calibration.h"


def load() -> dict:
    with TOML_PATH.open("rb") as f:
        return tomllib.load(f)


def render(cfg: dict) -> str:
    pwm = cfg["pwm"]
    ch = cfg["channels"]
    sx = cfg["servo"]["X"]
    sy = cfg["servo"]["Y"]
    sd = cfg["servo"]["SD"]
    id_ = cfg["servo"]["ID"]
    si = cfg["servo"]["SI"]
    ii = cfg["servo"]["II"]
    boot = cfg["boot"]
    lines = [
        "// Generado por scripts/generate_eyes_calibration.py desde config/eyes-calibration.toml.",
        "// No editar a mano. Fuente canonica: config/eyes-calibration.toml.",
        "#pragma once",
        "",
        f"#define EYES_PWM_HZ {pwm['frequency_hz']}",
        f"#define EYES_PULSE_0_US {pwm['pulse_0_us']}",
        f"#define EYES_PULSE_180_US {pwm['pulse_180_us']}",
        "",
        f"#define CH_X {ch['X']}",
        f"#define CH_Y {ch['Y']}",
        f"#define CH_SD {ch['SD']}",
        f"#define CH_ID {ch['ID']}",
        f"#define CH_SI {ch['SI']}",
        f"#define CH_II {ch['II']}",
        "",
        f"#define X_RIGHT {sx['right']}",
        f"#define X_CENTER {sx['center']}",
        f"#define X_LEFT {sx['left']}",
        f"#define Y_DOWN {sy['down']}",
        f"#define Y_CENTER {sy['center']}",
        f"#define Y_UP {sy['up']}",
        f"#define SD_OPEN {sd['open']}",
        f"#define SD_CLOSED {sd['closed']}",
        f"#define ID_OPEN {id_['open']}",
        f"#define ID_CLOSED {id_['closed']}",
        f"#define SI_OPEN {si['open']}",
        f"#define SI_CLOSED {si['closed']}",
        f"#define II_OPEN {ii['open']}",
        f"#define II_CLOSED {ii['closed']}",
        "",
        f"#define BOOT_X {boot['X']}",
        f"#define BOOT_Y {boot['Y']}",
        f"#define BOOT_SD {boot['SD']}",
        f"#define BOOT_ID {boot['ID']}",
        f"#define BOOT_SI {boot['SI']}",
        f"#define BOOT_II {boot['II']}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    cfg = load()
    content = render(cfg)
    if "--check" in sys.argv:
        current = HEADER_PATH.read_text(encoding="utf-8") if HEADER_PATH.exists() else ""
        if current != content:
            print("calibration.h desactualizado: ejecuta scripts/generate_eyes_calibration.py")
            return 1
        print("calibration.h al dia")
        return 0
    HEADER_PATH.write_text(content, encoding="utf-8")
    print(f"generado {HEADER_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
