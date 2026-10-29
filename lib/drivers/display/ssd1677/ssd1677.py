# SSD1677 e-paper controller driving 800x480 glass, as on the Seeed reTerminal Sticky. Every
# refresh is draftling's differential one (0x22 FC), which ghosts least on a Sticky; a full
# refresh is the same waveform with every pixel marked as changed.

import time

import micropython
from micropython import const

WIDTH = const(800)
HEIGHT = const(480)
_PLANE = const(WIDTH * HEIGHT // 8)
_SLICE = const(4096)

_DRIVER_OUTPUT = const(0x01)
_BOOSTER = const(0x0C)
_DEEP_SLEEP = const(0x10)
_DATA_ENTRY = const(0x11)
_SW_RESET = const(0x12)
_TEMP_SENSOR = const(0x18)
_ACTIVATE = const(0x20)
_UPDATE_1 = const(0x21)
_UPDATE_2 = const(0x22)
_RAM_NEW = const(0x24)
_RAM_OLD = const(0x26)
_BORDER = const(0x3C)
_X_WINDOW = const(0x44)
_Y_WINDOW = const(0x45)
_FILL_OLD = const(0x46)
_FILL_NEW = const(0x47)
_X_COUNTER = const(0x4E)
_Y_COUNTER = const(0x4F)


@micropython.viper
def _invert(dst: ptr8, src: ptr8, start: int, n: int):
    for i in range(n):
        dst[i] = src[start + i] ^ 0xFF


class SSD1677:
    """Frames are 800x480 MONO_HLSB buffers of 48,000 bytes, with 1 for white."""

    def __init__(self, spi, cs, dc, rst, busy, timeout_ms=10_000):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self._busy = busy
        self.timeout_ms = timeout_ms
        cs.init(cs.OUT, value=1)
        dc.init(dc.OUT, value=0)
        rst.init(rst.OUT, value=1)
        busy.init(busy.IN, None)
        self._cmd = bytearray(1)
        self._buf = bytearray(_SLICE)

    def init(self):
        """Reset the controller and fill both planes white. The first show() must be full."""
        self.rst(0)
        time.sleep_ms(10)
        self.rst(1)
        time.sleep_ms(10)
        self._command(_SW_RESET)
        # BUSY may not rise in time for the first sample.
        time.sleep_ms(10)
        self.wait()
        self._command(_TEMP_SENSOR, b"\x80")
        self._command(_BOOSTER, b"\xae\xc7\xc3\xc0\x80")
        self._command(_DRIVER_OUTPUT, b"\xdf\x01\x02")
        self._command(_BORDER, b"\x80")
        # The glass's gates run bottom to top, so rows count down from the last one.
        self._command(_DATA_ENTRY, b"\x01")
        self._command(_X_WINDOW, b"\x00\x00\x1f\x03")
        self._command(_Y_WINDOW, b"\xdf\x01\x00\x00")
        self._home()
        self._command(_FILL_OLD, b"\xf7")
        self.wait()
        self._command(_FILL_NEW, b"\xf7")
        self.wait()

    def busy(self):
        return self._busy() == 1

    def wait(self, timeout_ms=None):
        start = time.ticks_ms()
        while self.busy():
            self._check(start, timeout_ms)
            time.sleep_ms(1)

    async def wait_async(self, timeout_ms=None):
        import asyncio

        start = time.ticks_ms()
        while self.busy():
            self._check(start, timeout_ms)
            await asyncio.sleep_ms(10)

    def show(self, frame, old=None):
        """Start a refresh to frame and return without waiting for it.

        old is what the glass shows now, and only pixels that differ from it change. Without it
        every pixel is driven: a full refresh.
        """
        if len(frame) != _PLANE or old is not None and len(old) != _PLANE:
            raise ValueError("frame size")
        self.wait()
        self._plane(_RAM_NEW, frame)
        if old is None:
            self._inverse_plane(_RAM_OLD, frame)
        else:
            self._plane(_RAM_OLD, old)
        self._command(_UPDATE_1, b"\x00")
        self._command(_BORDER, b"\xc0")
        # Mode 2 with the analog supply left on, so a burst doesn't power-cycle it each frame.
        self._command(_UPDATE_2, b"\xfc")
        self._command(_ACTIVATE)
        time.sleep_ms(2)

    def sleep(self):
        """Power down and sleep, losing both planes. Wake with init(), then a full show()."""
        self._wait_capped()
        self._command(_BORDER, b"\x80")
        self._command(_UPDATE_2, b"\x03")
        self._command(_ACTIVATE)
        time.sleep_ms(2)
        self._wait_capped()
        self._command(_DEEP_SLEEP, b"\x03")

    # draftling caps these waits at 3 s, after one hung for its full 30 s: sleep goes ahead.
    def _wait_capped(self):
        try:
            self.wait(3000)
        except OSError:
            pass

    def _check(self, start, timeout_ms):
        if timeout_ms is None:
            timeout_ms = self.timeout_ms
        if time.ticks_diff(time.ticks_ms(), start) >= timeout_ms:
            raise OSError("SSD1677 busy timeout")

    def _begin(self, cmd):
        self.cs(0)
        self.dc(0)
        self._cmd[0] = cmd
        self.spi.write(self._cmd)
        self.dc(1)

    # CS goes high even on Ctrl-C mid-transfer, or the panel would hear the SD card's traffic.
    def _command(self, cmd, data=None):
        try:
            self._begin(cmd)
            if data:
                self.spi.write(data)
        finally:
            self.cs(1)

    def _home(self):
        self._command(_X_COUNTER, b"\x00\x00")
        self._command(_Y_COUNTER, b"\xdf\x01")

    def _plane(self, cmd, frame):
        self._home()
        self._command(cmd, frame)

    def _inverse_plane(self, cmd, frame):
        self._home()
        buf = self._buf
        try:
            self._begin(cmd)
            for start in range(0, _PLANE, _SLICE):
                n = min(_SLICE, _PLANE - start)
                _invert(buf, frame, start, n)
                self.spi.write(buf if n == _SLICE else memoryview(buf)[:n])
        finally:
            self.cs(1)
