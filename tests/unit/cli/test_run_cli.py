from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from sirah.cli.run import build_parser


def test_parser_accepts_camera_and_yunet_model():
    args = build_parser().parse_args(
        ["--camera-device", "/dev/video0", "--yunet-model", "models/yunet/model.onnx"]
    )
    assert args.camera_device == "/dev/video0"
    assert args.yunet_model == "models/yunet/model.onnx"


def test_parser_accepts_jsonl_replay_and_yunet_model():
    args = build_parser().parse_args(
        ["--replay-jsonl", "frames.jsonl", "--yunet-model", "model.onnx"]
    )
    assert args.replay_jsonl == "frames.jsonl"
    assert args.yunet_model == "model.onnx"


def test_sigterm_stops_the_runtime_cleanly(tmp_path):
    env = dict(os.environ)
    env["SIRAH_CONFIG"] = "config/runtime.toml"
    env["SIRAH_ACTUATORS"] = "config/actuators.yaml"
    process = subprocess.Popen(
        [sys.executable, "-m", "sirah.cli.run", "--fake"],
        cwd=Path(__file__).parents[3],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(1.5)  # give the runtime a moment to boot and start heartbeats
    process.send_signal(signal.SIGTERM)
    try:
        returncode = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        raise AssertionError("sirah-runtime did not stop on SIGTERM within 10s")
    assert returncode == 0
    assert process.stderr.read().strip() == ""
