"""In-memory audio doubles for offline tests and replay."""

from __future__ import annotations

from collections.abc import Sequence

from sirah.audio.contracts import AudioChunk, Transcript


class FakeAudioSource:
    def __init__(
        self,
        chunks: Sequence[AudioChunk] = (),
        *,
        fail_at: int | None = None,
        failure: Exception | None = None,
    ) -> None:
        self._chunks = tuple(chunks)
        self._fail_at = fail_at
        self._failure = failure
        self._index = 0
        self._started = False

    async def start(self) -> None:
        self._started = True

    async def next_chunk(self) -> AudioChunk | None:
        if not self._started:
            raise RuntimeError("audio source has not started")
        if self._fail_at == self._index:
            raise self._failure or RuntimeError("fake audio source failed")
        if self._index >= len(self._chunks):
            return None
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk

    async def stop(self) -> None:
        self._started = False


class FakeSTT:
    def __init__(self, transcript: Transcript, *, failure: Exception | None = None) -> None:
        self._transcript = transcript
        self._failure = failure
        self.requests: list[tuple[AudioChunk, ...]] = []

    async def transcribe(self, chunks: Sequence[AudioChunk]) -> Transcript:
        self.requests.append(tuple(chunks))
        if self._failure is not None:
            raise self._failure
        return self._transcript


class FakeTTS:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self._failure = failure
        self.spoken: list[str] = []

    async def speak(self, text: str) -> None:
        if self._failure is not None:
            raise self._failure
        self.spoken.append(text)
