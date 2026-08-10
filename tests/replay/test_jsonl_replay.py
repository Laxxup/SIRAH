from __future__ import annotations

import json
from pathlib import Path

from sirah.perception.replay import JsonlReplayCameraSource, VideoReplayCameraSource


async def test_jsonl_replay_resolves_relative_image_paths(tmp_path):
    image = tmp_path / "frame-000.pgm"
    image.write_bytes(b"P2\n1 1\n255\n0\n")
    manifest = tmp_path / "frames.jsonl"
    manifest.write_text(json.dumps({"image": image.name, "label": "empty"}) + "\n")

    source = JsonlReplayCameraSource(manifest)
    await source.start()
    frame = await source.next_frame()

    assert frame is not None
    assert frame.index == 0
    assert frame.payload == {"image": image, "label": "empty"}
    assert await source.next_frame() is None


async def test_versioned_fixture_is_replayable():
    manifest = Path(__file__).parent / "fixtures" / "frames.jsonl"
    source = JsonlReplayCameraSource(manifest)
    await source.start()
    frame = await source.next_frame()
    assert frame is not None
    assert frame.payload["image"].is_file()


async def test_video_replay_returns_frames_then_eof(tmp_path):
    video = tmp_path / "session.mp4"
    video.touch()

    class FakeCapture:
        def __init__(self):
            self.frames = iter(["one", "two"])
            self.released = False

        def isOpened(self):
            return True

        def read(self):
            try:
                return True, next(self.frames)
            except StopIteration:
                return False, None

        def release(self):
            self.released = True

    capture = FakeCapture()
    source = VideoReplayCameraSource(video, capture_factory=lambda _: capture)
    await source.start()
    assert (await source.next_frame()).payload == "one"
    assert (await source.next_frame()).payload == "two"
    assert await source.next_frame() is None
    await source.stop()
    assert capture.released
