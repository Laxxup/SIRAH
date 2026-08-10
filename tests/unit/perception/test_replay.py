from __future__ import annotations

from sirah.perception.replay import ReplayCameraSource


async def test_replay_returns_frames_then_eof():
    source = ReplayCameraSource(["first", "second"])
    await source.start()

    first = await source.next_frame()
    second = await source.next_frame()
    eof = await source.next_frame()

    assert first is not None and first.index == 0 and first.payload == "first"
    assert second is not None and second.index == 1 and second.payload == "second"
    assert eof is None


async def test_replay_stop_ends_stream_early():
    source = ReplayCameraSource(["frame"])
    await source.start()
    await source.stop()
    assert await source.next_frame() is None
