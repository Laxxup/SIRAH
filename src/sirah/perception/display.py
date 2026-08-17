"""Display backends for the graphical diagnostic viewer (M5.2B).

The backend is the only component that talks to a windowing/viewer
process. It is deliberately decoupled from perception: it renders nothing,
owns no camera and never blocks the perception loop.

Backend contract:

- `show(frame)` is non-blocking. If the viewer cannot keep up it DROPS
  intermediate frames (the latest frame always wins), so a slow display
  never creates a growing backlog and never slows perception down.
- `user_closed` becomes True when the viewer process exits on its own
  (ffplay `q`/Esc/window close) or the display pipe breaks — callers use
  this to shut the whole preview down cleanly.
- `close()` is idempotent, always reaps the child process and never
  leaves a zombie or an unbounded writer queue.

Only the ffplay backend is implemented (M5.2B decision: it preserves the
production `opencv-python-headless` dependency — the renderer uses only
imgproc primitives — and keeps ffplay an optional external binary, never
a core runtime dependency). The `DisplayBackend` protocol is the seam a
future HighGUI/SDL backend could plug into.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from collections.abc import Callable
from typing import Protocol, runtime_checkable

_LOGGER = logging.getLogger(__name__)
_FFPLAY_ARGS: tuple[str, ...] = (
    "-loglevel",
    "error",
    "-window_title",
    "SIRAH perception preview",
    "-framerate",
    "30",
)


@runtime_checkable
class DisplayBackend(Protocol):
    """Non-blocking latest-frame display consumer."""

    def show(self, frame: object) -> None: ...

    @property
    def user_closed(self) -> bool: ...

    def close(self) -> None: ...


class FfplayDisplayBackend:
    """Pipes annotated BGR frames to an external `ffplay` process.

    A single writer thread owns the child's stdin. `show()` only replaces
    a one-slot buffer; the writer thread picks up the newest frame and
    blocks on the OS pipe until ffplay drains it (perception never waits
    on that pipe). When the child exits or the pipe breaks, the writer
    marks `user_closed` and stops, so the owning loop can detect it.

    The executable is located at construction time and reported as an
    actionable error when missing — ffplay stays an optional, external,
    explicitly-invoked binary (no `shell=True`, no core dependency).
    """

    def __init__(
        self,
        *,
        executable: str = "ffplay",
        which: Callable[[str], str | None] | None = None,
        pix_fmt: str = "bgr24",
    ) -> None:
        finder = which or _which_ffplay
        found = finder(executable)
        if found is None:
            raise RuntimeError(
                "graphical preview requires the external 'ffplay' executable "
                "(part of FFmpeg); install ffmpeg or drop --preview-window"
            )
        self._executable_path: str = found
        self._pix_fmt = pix_fmt
        self._proc: subprocess.Popen[bytes] | None = None
        self._latest: object | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._user_closed = False
        self._closed = False
        self._lock = threading.Lock()
        self._writer = threading.Thread(
            target=self._writer_loop, name="sirah-display", daemon=True
        )
        self._writer.start()

    # -- DisplayBackend --------------------------------------------------

    def show(self, frame: object) -> None:
        """Store the newest frame; the writer sends it (dropping others)."""
        with self._lock:
            if self._closed:
                return
            self._latest = frame
        self._wake.set()

    @property
    def user_closed(self) -> bool:
        return self._user_closed

    def close(self) -> None:
        """Idempotent teardown: close stdin, reap the child, join the writer."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
            proc = self._proc
            self._proc = None
        self._wake.set()
        writer = self._writer
        if proc is not None:
            try:
                stdin = proc.stdin
                if stdin is not None and not stdin.closed:
                    stdin.close()  # EOF: ffplay exits on its own
            except OSError:
                pass
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    pass  # daemon thread will reap on exit
        if writer is not None:
            writer.join(timeout=3.0)

    def _writer_loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=0.1)
            self._wake.clear()
            with self._lock:
                frame = self._latest
                self._latest = None
            if frame is None:
                continue
            try:
                import numpy as np

                array = np.ascontiguousarray(frame)
            except Exception as exc:  # noqa: BLE001 - non-image frame; skip it
                _LOGGER.debug("display skipped non-image frame: %s", exc)
                continue
            if array.ndim != 3 or array.shape[2] not in (3, 4):
                continue
            height, width = array.shape[:2]
            with self._lock:
                if self._stop.is_set():
                    return
                self._ensure_started(width, height)
                proc = self._proc
            if proc is None or proc.stdin is None:
                continue
            if self._child_exited(proc):
                self._user_closed = True
                return
            try:
                proc.stdin.write(array.tobytes())
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                # viewer closed the pipe: normal user-closed condition
                self._user_closed = True
                return
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc is not None and proc.stdin is not None:
            try:
                if not proc.stdin.closed:
                    proc.stdin.close()
            except OSError:
                pass

    def _ensure_started(self, width: int, height: int) -> None:
        """Start the ffplay child once, sized to the first displayed frame."""
        if self._proc is not None:
            return
        if width <= 0 or height <= 0:
            raise ValueError("frame dimensions must be positive")
        args = [
            self._executable_path,
            "-f",
            "rawvideo",
            "-pixel_format",
            self._pix_fmt,
            "-video_size",
            f"{width}x{height}",
            *_FFPLAY_ARGS,
            "-i",
            "pipe:0",
        ]
        # no shell=True; explicit argv only (no command injection surface)
        self._proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @staticmethod
    def _child_exited(proc: subprocess.Popen[bytes]) -> bool:
        return proc.poll() is not None


def _which_ffplay(executable: str) -> str | None:
    from shutil import which

    found = which(executable)
    if found is None:
        return None
    if os.access(found, os.X_OK):
        return found
    return None
