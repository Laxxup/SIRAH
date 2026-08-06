"""Test Web Lab audio preparation helpers."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import sirah
import sirah.web_server as web_server


def test_prepare_audio_converts_browser_recording(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    converted = b"RIFF converted wav"
    monkeypatch.setattr(web_server, "_convert_to_wav", lambda data: converted)

    assert web_server._prepare_audio(b"browser webm") == converted


def test_prepare_audio_keeps_wav_without_conversion(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fail_conversion(data: bytes) -> bytes:
        raise AssertionError("WAV must not be converted")

    monkeypatch.setattr(web_server, "_convert_to_wav", fail_conversion)

    wav = b"RIFF native wav"
    assert web_server._prepare_audio(wav) == wav


def test_prepare_audio_returns_none_when_conversion_fails(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(web_server, "_convert_to_wav", lambda data: None)

    assert web_server._prepare_audio(b"invalid browser audio") is None


def test_run_async_dispatches_to_dedicated_loop(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever)
    thread.start()
    monkeypatch.setattr(web_server, "_loop", loop)

    try:
        result = web_server._run_async(asyncio.sleep(0, result="ok"))
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1)
        loop.close()

    assert result == "ok"


def test_parse_arecord_output_returns_capture_devices() -> None:
    output = """**** List of CAPTURE Hardware Devices ****
card 0: PCH [HDA Intel PCH], device 0: ALC3204 Analog [ALC3204 Analog]
  Subdevices: 1/1
"""

    assert web_server._parse_arecord_output(output) == [
        "card 0: PCH [HDA Intel PCH], device 0: ALC3204 Analog [ALC3204 Analog]"
    ]


def test_web_assets_live_inside_sirah_package() -> None:
    package_dir = Path(sirah.__file__).parent

    assert package_dir / "web" / "templates" == web_server.TEMPLATE_DIR
    assert package_dir / "web" / "static" == web_server.STATIC_DIR
    assert (web_server.TEMPLATE_DIR / "index.html").is_file()
    assert (web_server.STATIC_DIR / "style.css").is_file()


@pytest.fixture(scope="module")
def web_app():  # type: ignore[no-untyped-def]
    app = web_server.create_app(
        intelligence_type="laboratory",
        tts="fake",
        start_camera=False,
    )
    yield app

    if web_server._system is not None:
        web_server._run_async(web_server._system.orchestrator.stop())
    loop = web_server._loop
    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(loop.stop)
    if web_server._loop_thread is not None:
        web_server._loop_thread.join(timeout=2)
    if loop is not None and not loop.is_closed():
        loop.close()


def test_index_route_serves_web_lab_without_camera(web_app) -> None:  # type: ignore[no-untyped-def]
    response = web_app.test_client().get("/")

    assert response.status_code == 200
    assert b"SIRAH Web Lab" in response.data


def test_status_route_reports_no_camera_when_disabled(web_app) -> None:  # type: ignore[no-untyped-def]
    response = web_app.test_client().get("/api/status")

    assert response.status_code == 200
    assert response.json["ok"] is True
    assert response.json["vision_active"] is False
    assert response.json["diagnostics"]
    assert response.json["diagnostics"][0] == {
        "id": "core/orchestrator",
        "kind": "core",
        "name": "orchestrator",
        "status": "ready",
        "detail": "started",
    }


def test_overlay_route_reports_empty_mapping_without_camera(web_app) -> None:  # type: ignore[no-untyped-def]
    response = web_app.test_client().get("/api/overlay")

    assert response.status_code == 200
    assert response.json == {
        "ok": True,
        "active": False,
        "faces": [],
        "hands": [],
        "context": "",
    }


def test_serialize_overlay_keeps_detection_mapping_and_context() -> None:
    face = SimpleNamespace(bbox=(0.1, 0.2, 0.3, 0.4), confidence=0.9)
    face_context = SimpleNamespace(
        dominant_color="verde",
        smiling=True,
        smile_score=0.8,
        torso_bbox=(0.1, 0.6, 0.3, 0.3),
        face_position="centro",
        face_distance="media",
    )
    hand = SimpleNamespace(
        bbox=(0.5, 0.2, 0.2, 0.5),
        handedness="Left",
        fingers=(True, False, True, False, False),
        finger_count=2,
    )
    vision_loop = SimpleNamespace(
        _running=True,
        _latest_faces=(face,),
        _latest_visual_ctx=SimpleNamespace(
        face_contexts=(face_context,),
            hands=SimpleNamespace(hands=(hand,)),
        ),
        vision_description="ropa verde, sonriendo, 2 dedos extendidos confirmados",
    )

    assert web_server._serialize_overlay(vision_loop) == {
        "ok": True,
        "active": True,
        "faces": [{
            "index": 1,
            "bbox": [0.1, 0.2, 0.3, 0.4],
            "confidence": 0.9,
            "color": "verde",
            "smiling": True,
            "smile_score": 0.8,
            "torso_bbox": [0.1, 0.6, 0.3, 0.3],
            "position": "centro",
            "distance": "media",
        }],
        "hands": [{
            "index": 1,
            "bbox": [0.5, 0.2, 0.2, 0.5],
            "handedness": "Left",
            "fingers": [True, False, True, False, False],
            "finger_count": 2,
        }],
        "context": "ropa verde, sonriendo, 2 dedos extendidos confirmados",
    }
