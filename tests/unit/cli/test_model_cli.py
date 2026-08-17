from __future__ import annotations

from sirah.cli import models


def test_models_cli_installs_yunet(tmp_path, monkeypatch, capsys):
    destination = tmp_path / "models"
    expected = destination / "face_detection_yunet_2023mar.onnx"
    monkeypatch.setattr(models, "install_yunet", lambda path: expected)

    assert models.main(["yunet", "--destination", str(destination)]) == 0
    assert capsys.readouterr().out.strip() == str(expected)


def test_models_cli_installs_gesture(tmp_path, monkeypatch, capsys):
    destination = tmp_path / "models"
    expected = destination / "gesture_recognizer.task"
    monkeypatch.setattr(models, "install_gesture", lambda path: expected)

    assert models.main(["gesture", "--destination", str(destination)]) == 0
    assert capsys.readouterr().out.strip() == str(expected)
