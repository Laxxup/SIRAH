from __future__ import annotations

from sirah.cli.run import build_parser


def test_parser_accepts_camera_and_yunet_model():
    args = build_parser().parse_args(
        ["--camera-device", "/dev/video0", "--yunet-model", "models/yunet/model.onnx"]
    )
    assert args.camera_device == "/dev/video0"
    assert args.yunet_model == "models/yunet/model.onnx"
