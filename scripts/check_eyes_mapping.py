#!/usr/bin/env python3
"""Verifica que config/eyes-calibration.toml respeta la calibracion validada.

Sin dependencias. Uso: python3 scripts/check_eyes_mapping.py
Comprueba: pulsos, centros, mapeo segmentado -1/0/+1, boot, canales.
"""
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {
    ("pwm", "frequency_hz"): 50,
    ("pwm", "pulse_0_us"): 1000,
    ("pwm", "pulse_180_us"): 2000,
    ("channels", "X"): 0, ("channels", "Y"): 1,
    ("channels", "SD"): 2, ("channels", "ID"): 3,
    ("channels", "SI"): 4, ("channels", "II"): 5,
    ("servo", "X", "right"): 60, ("servo", "X", "center"): 120, ("servo", "X", "left"): 180,
    ("servo", "Y", "down"): 15, ("servo", "Y", "center"): 30, ("servo", "Y", "up"): 60,
    ("servo", "SD", "open"): 110, ("servo", "SD", "closed"): 15,
    ("servo", "ID", "open"): 120, ("servo", "ID", "closed"): 180,
    ("servo", "SI", "open"): 50, ("servo", "SI", "closed"): 145,
    ("servo", "II", "open"): 110, ("servo", "II", "closed"): 50,
    ("boot", "X"): 120, ("boot", "Y"): 30,
    ("boot", "SD"): 110, ("boot", "ID"): 120, ("boot", "SI"): 50, ("boot", "II"): 110,
}


def get(cfg, path):
    node = cfg
    for key in path:
        node = node[key]
    return node


def seg(t, lo, center, hi):
    # Replica targetToAngleX/Y del firmware: segmentos alrededor del centro.
    if t < 0:
        return round(center + t * (center - lo))
    return round(center + t * (hi - center))


def main() -> int:
    with (ROOT / "config" / "eyes-calibration.toml").open("rb") as f:
        cfg = tomllib.load(f)
    errors = []
    for path, want in EXPECTED.items():
        if get(cfg, path) != want:
            errors.append(f"{'.'.join(map(str, path))}: {get(cfg, path)} != {want}")
    # Mapeo segmentado preserva el centro calibrado (no lineal unico).
    x = cfg["servo"]["X"]
    y = cfg["servo"]["Y"]
    if (seg(-1, x["left"], x["center"], x["right"]),
            seg(0, x["left"], x["center"], x["right"]),
            seg(1, x["left"], x["center"], x["right"])) != (180, 120, 60):
        errors.append("mapeo X -1/0/+1 no da 180/120/60")
    if (seg(-1, y["down"], y["center"], y["up"]),
            seg(0, y["down"], y["center"], y["up"]),
            seg(1, y["down"], y["center"], y["up"])) != (15, 30, 60):
        errors.append("mapeo Y -1/0/+1 no da 15/30/60")
    # pulse_us = 1000 + angle * (1000/180)
    for angle, want in ((0, 1000), (110, 1611), (180, 2000)):
        if 1000 + angle * 1000 // 180 != want:
            errors.append(f"pulso {angle} != {want}")
    tired_expected = {"SD": 63, "ID": 150, "SI": 98, "II": 80}
    for name, want in tired_expected.items():
        servo = cfg["servo"][name]
        tired = (servo["open"] + servo["closed"] + 1) // 2
        if tired != want or not min(servo.values()) <= tired <= max(servo.values()):
            errors.append(f"pose tired {name}: {tired} != {want} o fuera de limites")
    if errors:
        print("FAIL:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("OK: calibracion canonica y mapeo segmentado verificados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
