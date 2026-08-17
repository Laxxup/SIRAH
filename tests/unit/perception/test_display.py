"""Display backend tests (M5.2B): ffplay subprocess lifecycle, latest-frame
drop, idempotent close, no shell, and the actionable missing-executable
error. Tests never spawn a real ffplay window: the child process is faked
via an executable shim so the suite stays display-free and deterministic.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from sirah.perception.display import FfplayDisplayBackend


@pytest.fixture
def shim_dir(tmp_path: Path) -> Path:
    """A fake `ffplay` executable that records its argv and feeds stdin."""
    script = (
        "#!/bin/sh\n"
        'echo "$@" > "$SHIM_MARKER"\n'
        "cat > /dev/null\n"
    )
    exe = tmp_path / "ffplay"
    exe.write_text(script)
    exe.chmod(0o755)
    return tmp_path


def _which_shim(executable: str) -> str | None:
    return None if executable == "ffplay" else "/does/not/exist"


def test_missing_executable_raises_actionable_error(monkeypatch, tmp_path):
    from sirah.perception import display as display_mod

    def missing(_executable: str) -> str | None:
        return None

    monkeypatch.setattr(display_mod, "_which_ffplay", missing)
    with pytest.raises(RuntimeError, match="ffplay"):
        FfplayDisplayBackend()


def test_constructor_accepts_explicit_executable(tmp_path):
    backend = FfplayDisplayBackend(
        executable=str(tmp_path / "ffplay"), which=lambda _: str(tmp_path / "ffplay")
    )
    assert not backend.user_closed
    backend.close()
    assert backend.user_closed is False


def test_latest_frame_wins_and_closes_idempotently(shim_dir, tmp_path):
    marker = tmp_path / "spawned"
    backend = FfplayDisplayBackend(
        executable=str(shim_dir / "ffplay"),
        which=lambda _: str(shim_dir / "ffplay"),
    )
    args: list[str] = []

    def fake_ensure(width: int, height: int) -> None:
        argv = [
            str(shim_dir / "ffplay"),
            "-f", "rawvideo", "-pixel_format", "bgr24", "-video_size", f"{width}x{height}",
            "-loglevel", "error", "-window_title", "SIRAH perception preview",
            "-framerate", "30", "-i", "pipe:0",
        ]
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "SHIM_MARKER": str(marker)},
        )
        backend._proc = proc
        args.extend(argv)

    backend._ensure_started = fake_ensure  # type: ignore[method-assign]
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    backend.show(frame)
    backend.show(frame)  # dropped in favor of the latest
    time.sleep(0.5)
    assert marker.exists()
    backend.close()
    backend.close()  # idempotent
    assert backend._proc is None or backend._proc.poll() is not None


def test_show_after_close_is_a_noop(shim_dir):
    backend = FfplayDisplayBackend(
        executable=str(shim_dir / "ffplay"),
        which=lambda _: str(shim_dir / "ffplay"),
    )
    backend.close()
    backend.show(np.zeros((1, 1, 3), dtype=np.uint8))  # must not raise


def test_broken_pipe_marks_user_closed(shim_dir, tmp_path):
    """When the child exits, the writer marks user_closed and stops."""
    backend = FfplayDisplayBackend(
        executable=str(shim_dir / "ffplay"),
        which=lambda _: str(shim_dir / "ffplay"),
    )

    def fake_ensure(width: int, height: int) -> None:
        # A child that immediately exits -> the writer's write fails.
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.exit(0)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        backend._proc = proc

    backend._ensure_started = fake_ensure  # type: ignore[method-assign]
    backend.show(np.zeros((240, 320, 3), dtype=np.uint8))
    deadline = time.monotonic() + 5.0
    while not backend.user_closed and time.monotonic() < deadline:
        time.sleep(0.05)
    assert backend.user_closed
    backend.close()


def test_no_shell_true_is_used(monkeypatch, tmp_path):
    """The child must be spawned with explicit argv, never a shell."""
    from sirah.perception import display as display_mod

    seen: dict[str, object] = {}

    class _FakeStdin:
        closed = False

        def close(self):
            self.closed = True

    class _FakePopen:
        def __init__(self):
            self.stdin = _FakeStdin()
            self.stdout = None
            self.stderr = None

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    def fake_popen(args, **kwargs):
        seen["args"] = args
        seen["shell"] = kwargs.get("shell", False)
        return _FakePopen()

    monkeypatch.setattr(display_mod.subprocess, "Popen", fake_popen)
    backend = FfplayDisplayBackend(
        executable="/usr/bin/ffplay",
        which=lambda _: "/usr/bin/ffplay",
    )
    backend._proc = None

    # force a resize so the backend starts the child through our shim
    backend._ensure_started(320, 240)
    assert seen["shell"] is False
    assert seen["args"][0] == "/usr/bin/ffplay"
    assert "pipe:0" in seen["args"]
    backend.close()