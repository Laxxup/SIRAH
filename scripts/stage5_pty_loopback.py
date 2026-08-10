"""One-off loopback evidence for Stage 5 (NOT a CI test).

Opens a pseudo-tty pair, runs the real SerialTransport (pyserial-asyncio)
against the slave side and echoes lines from the master side, proving the
adapter works end-to-end with the real serial stack, hardware-free.
Run: python3 scripts/stage5_pty_loopback.py
"""

from __future__ import annotations

import asyncio
import os
import pty

from sirah.hardware.serial_adapter import SerialTransport


async def main() -> None:
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)

    async def factory(device: str, baudrate: int) -> None:
        raise AssertionError("real transport must be opened by pyserial")

    transport = SerialTransport(slave_name, port_factory=None)  # real pyserial
    await transport.connect()
    print(f"connected to {slave_name}: {transport.status()}")

    async def echo_loop() -> None:
        while True:
            data = await asyncio.to_thread(os.read, master_fd, 256)
            if not data:
                return
            os.write(master_fd, data)  # echo back

    echo = asyncio.create_task(echo_loop())

    await transport.send(b"TARGET 0.5 -0.25")
    line = await transport.read(timeout=2.0)
    print(f"echoed: {line!r}")
    assert line == b"TARGET 0.5 -0.25"

    await transport.send(b"STATUS")
    line = await transport.read(timeout=2.0)
    print(f"echoed: {line!r}")

    echo.cancel()
    await transport.disconnect()
    os.close(master_fd)
    os.close(slave_fd)
    print("LOOPBACK OK")


if __name__ == "__main__":
    asyncio.run(main())