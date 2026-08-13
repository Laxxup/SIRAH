from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from threading import Event, get_ident

import pytest

from sirah.audio.playback import PCMPlayer, SoundDevicePCMPlayer


async def test_player_delivers_pcm_to_injected_sink():
    delivered: list[bytes] = []

    async def sink(pcm: bytes) -> None:
        delivered.append(pcm)

    player = PCMPlayer(sink)
    await player.play("reply-1", b"pcm")
    await player.join()

    assert delivered == [b"pcm"]
    await player.close()


async def test_cancelling_an_operation_stops_active_and_drops_queued_pcm():
    started = asyncio.Event()
    released = asyncio.Event()
    delivered: list[bytes] = []

    async def sink(pcm: bytes) -> None:
        started.set()
        await released.wait()
        delivered.append(pcm)

    player = PCMPlayer(sink, queue_size=2)
    await player.play("reply-1", b"active")
    await started.wait()
    await player.play("reply-1", b"queued")

    await player.cancel("reply-1")
    released.set()
    await player.join()

    assert delivered == []
    await player.close()


async def test_player_keeps_queue_bounded_while_waiting_for_sink():
    started = asyncio.Event()
    released = asyncio.Event()
    delivered: list[bytes] = []

    async def sink(pcm: bytes) -> None:
        started.set()
        await released.wait()
        delivered.append(pcm)

    player = PCMPlayer(sink, queue_size=1)
    await player.play("reply-1", b"active")
    await started.wait()
    await player.play("reply-2", b"queued")
    blocked = asyncio.create_task(player.play("reply-3", b"blocked"))
    await asyncio.sleep(0)

    assert not blocked.done()

    await player.cancel("reply-3")
    with pytest.raises(asyncio.CancelledError):
        await blocked
    released.set()
    await player.join()
    assert delivered == [b"active", b"queued"]
    await player.close()


def test_bluealsa_playback_uses_alsa_subprocess(monkeypatch):
    calls = []
    player = SoundDevicePCMPlayer(device="bluealsa", sample_rate=24_000)

    monkeypatch.setattr(
        "sirah.audio.playback.subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    player._play(b"pcm")

    assert calls == [
        (
            (
                [
                    "aplay",
                    "-D",
                    "bluealsa",
                    "-f",
                    "S16_LE",
                    "-r",
                    "24000",
                    "-c",
                    "1",
                    "-t",
                    "raw",
                ],
            ),
            {"input": b"pcm", "check": True},
        )
    ]


async def test_player_streams_pcm_chunks_to_a_single_injected_sink():
    delivered: list[bytes] = []

    async def source() -> AsyncIterator[bytes]:
        yield b"first"
        yield b"last"

    async def sink(pcm: bytes) -> None:
        delivered.append(pcm)

    player = PCMPlayer(sink)

    await player.play_stream("reply-1", source())

    assert delivered == [b"first", b"last"]
    await player.close()


async def test_bluealsa_stream_uses_one_aplay_process(monkeypatch) -> None:
    processes = []

    class FakeInput:
        def __init__(self) -> None:
            self.writes: list[bytes] = []
            self.closed = False

        def write(self, pcm: bytes) -> None:
            self.writes.append(pcm)

        def flush(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs
            self.stdin = FakeInput()
            self.waited = False
            self.terminated = False
            processes.append(self)

        def wait(self) -> int:
            self.waited = True
            return 0

        def terminate(self) -> None:
            self.terminated = True

    async def source() -> AsyncIterator[bytes]:
        yield b"first"
        yield b"last"

    monkeypatch.setattr("sirah.audio.playback.subprocess.Popen", FakeProcess)
    player = SoundDevicePCMPlayer(device="bluealsa", sample_rate=24_000)

    await player.play_stream("reply-1", source())

    assert len(processes) == 1
    assert processes[0].stdin.writes == [b"first", b"last"]
    assert processes[0].stdin.closed is True
    assert processes[0].waited is True
    assert processes[0].terminated is False


async def test_sounddevice_player_keeps_one_output_stream_open_for_pcm_stream():
    calls: list[object] = []
    first_written = asyncio.Event()
    release_last = asyncio.Event()

    class FakeOutputStream:
        def start(self) -> None:
            calls.append("start")

        def write(self, pcm: bytes) -> None:
            calls.append(pcm)
            if pcm == b"first":
                first_written.set()

        def stop(self) -> None:
            calls.append("stop")

        def close(self) -> None:
            calls.append("close")

    async def source() -> AsyncIterator[bytes]:
        yield b"first"
        await release_last.wait()
        yield b"last"

    player = SoundDevicePCMPlayer(
        sample_rate=24_000,
        stream_factory=lambda **kwargs: (calls.append(kwargs), FakeOutputStream())[1],
    )

    playback = asyncio.create_task(player.play_stream("reply-1", source()))
    await first_written.wait()

    assert not playback.done()
    release_last.set()
    await playback

    assert calls == [
        {"samplerate": 24_000, "channels": 1, "dtype": "int16", "device": None, "latency": 0.3},
        "start",
        b"first",
        b"last",
        "stop",
        "close",
    ]


async def test_cancelling_stream_waits_for_write_before_owner_aborts_and_closes():
    calls: list[object] = []
    write_started = Event()
    release_write = Event()

    class BlockingRawOutputStream:
        def start(self) -> None:
            calls.append(("start", get_ident()))

        def write(self, _pcm: bytes) -> None:
            calls.append(("write", get_ident()))
            write_started.set()
            while not release_write.is_set():
                __import__("time").sleep(0.001)

        def abort(self) -> None:
            calls.append(("abort", get_ident()))

        def stop(self) -> None:
            calls.append(("stop", get_ident()))

        def close(self) -> None:
            calls.append(("close", get_ident()))

    async def source() -> AsyncIterator[bytes]:
        yield b"first"
        await asyncio.Event().wait()

    player = SoundDevicePCMPlayer(stream_factory=lambda **_kwargs: BlockingRawOutputStream())
    player._stop = lambda: None
    playback = asyncio.create_task(player.play_stream("turn-1", source()))
    await asyncio.to_thread(write_started.wait)

    await player.cancel("turn-1")
    playback.cancel()
    await asyncio.sleep(0)

    assert [name for name, _thread in calls] == ["start", "write"]
    release_write.set()
    with pytest.raises(asyncio.CancelledError):
        await playback

    assert [name for name, _thread in calls] == ["start", "write", "abort", "close"]
    assert len({thread for _name, thread in calls}) == 1
    await player.close()


def test_sounddevice_player_uses_raw_output_stream_for_byte_pcm(monkeypatch):
    created = []

    class FakeRawOutputStream:
        def __init__(self, **kwargs) -> None:
            created.append(kwargs)

        def start(self) -> None:
            return None

    class FakeSoundDevice:
        RawOutputStream = FakeRawOutputStream
        OutputStream = object

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", FakeSoundDevice())

    player = SoundDevicePCMPlayer(sample_rate=24_000)

    player._open_output_stream()

    assert created == [
        {"samplerate": 24_000, "channels": 1, "dtype": "int16", "device": None, "latency": 0.3}
    ]
