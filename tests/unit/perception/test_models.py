from __future__ import annotations

import io

import pytest

from sirah.perception import models


def test_install_yunet_writes_verified_model(tmp_path, monkeypatch):
    payload = b"yunet-model"
    monkeypatch.setattr(models, "YUNET_SHA256", models.sha256(payload).hexdigest())
    monkeypatch.setattr(models, "urlopen", lambda *_args, **_kwargs: io.BytesIO(payload))

    path = models.install_yunet(tmp_path)

    assert path == tmp_path / models.YUNET_FILENAME
    assert path.read_bytes() == payload


def test_install_yunet_rejects_checksum_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "urlopen", lambda *_args, **_kwargs: io.BytesIO(b"wrong"))

    with pytest.raises(ValueError, match="SHA-256"):
        models.install_yunet(tmp_path)
