# SSD1677 e-paper controller driving 800x480 glass, as on the Seeed reTerminal Sticky. Every
# refresh is draftling's differential one (0x22 FC), which ghosts least on a Sticky; a full
# refresh is the same waveform with every pixel marked as changed. show_grey() uses the
# controller's own four-grey waveform instead.

import time

import micropython
from micropython import const

WIDTH = const(800)
HEIGHT = const(480)
_PLANE = const(WIDTH * HEIGHT // 8)
_GREY_FRAME = const(WIDTH * HEIGHT // 4)
_SLICE = const(4096)

_DRIVER_OUTPUT = const(0x01)
_BOOSTER = const(0x0C)
_DEEP_SLEEP = const(0x10)
_DATA_ENTRY = const(0x11)
_SW_RESET = const(0x12)
_TEMP_SENSOR = const(0x18)
_TEMP_WRITE = const(0x1A)
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


@micropython.viper
def _fill(dst: ptr8, value: int, start: int, n: int):
    for i in range(n):
        dst[i] = value


# Grey planes in Seeed_GFX2's encoding (level 0 black to 3 white): RAM 0x24 has a 1 where the
# level's high bit is clear (0 or 1), RAM 0x26 where its low bit is (0 or 2). GS2_HMSB keeps a
# byte's leftmost pixel in its lowest two bits; MONO_HLSB, in bit 7; a table's nibble, in bit 3.
def _clear_bits(bit):
    return bytes(sum(((~b >> (2 * k + bit)) & 1) << (3 - k) for k in range(4)) for b in range(256))


_HIGH_CLEAR = _clear_bits(1)
_LOW_CLEAR = _clear_bits(0)


@micropython.viper
def _grey_plane(dst: ptr8, src: ptr8, start: int, n: int, table: ptr8):
    for i in range(n):
        j = 2 * (start + i)
        dst[i] = (table[src[j]] << 4) | table[src[j + 1]]


class SSD1677:
    """Frames are 800x480 MONO_HLSB buffers of 48,000 bytes, with 1 for white. Grey frames are
    800x480 GS2_HMSB buffers of 96,000 bytes, 0 black to 3 white."""

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
        self._asleep = False
        self._powered = False
        # The glass may not match the planes (greys, or a transfer cut short), so the next show()
        # drives every pixel. init() leaves it alone; only a show() that gets as far as starting
        # its refresh clears it.
        self._stale = False
        # An init() cut short (reset may still be held) is run again before the next refresh.
        self._init_pending = False

    def init(self):
        """Reset the controller and fill both planes white. The first show() must be full."""
        self._init_pending = True
        self.rst(0)
        time.sleep_ms(10)
        self.rst(1)
        time.sleep_ms(10)
        self._asleep = False
        self._powered = False
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
        self._init_pending = False

    # In deep sleep BUSY stays high, though nothing is running.
    def busy(self):
        return not self._asleep and self._busy() == 1

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
        every pixel is driven: a full refresh. It is full whatever old is after show_grey(), or a
        show() cut short. A sleeping panel, or one whose init() was cut short, gets init() first.
        """
        if len(frame) != _PLANE or old is not None and len(old) != _PLANE:
            raise ValueError("frame size")
        if self._asleep or self._init_pending:
            self.init()
        self.wait()
        if self._stale:
            old = None
        self._stale = True
        self._plane(_RAM_NEW, frame)
        if old is None:
            self._converted_plane(_RAM_OLD, _invert, frame)
        else:
            self._plane(_RAM_OLD, old)
        self._command(_UPDATE_1, b"\x00")
        self._command(_BORDER, b"\xc0")
        # Mode 2 with the analog supply left on, so a burst doesn't power-cycle it each frame.
        self._command(_UPDATE_2, b"\xfc")
        # Unknown while 0x20 goes out: cut short here, the supply may be on or off.
        self._powered = None
        self._command(_ACTIVATE)
        self._powered = True
        self._stale = False
        time.sleep_ms(2)

    def show_grey(self, frame):
        """Start a four-grey refresh to frame (about 1.2 s) and return without waiting for it.

        frame is an 800x480 GS2_HMSB buffer, read only during the call. The controller is reset
        first. A partial can't clear greys, so the next show() is full whatever old it's given.
        """
        if len(frame) != _GREY_FRAME:
            raise ValueError("frame size")
        self._restart()
        self._command(_BORDER, b"\x00")
        self._converted_plane(_RAM_NEW, _grey_plane, frame, _HIGH_CLEAR)
        self._converted_plane(_RAM_OLD, _grey_plane, frame, _LOW_CLEAR)
        self._command(_UPDATE_1, b"\x00")
        # Seeed_GFX2's and ESPHome's SSD1677 grey refresh: the forced temperature picks the OTP's
        # grey waveform, and 0x22 D7 runs it, then turns the analog supply off itself.
        self._command(_TEMP_WRITE, b"\x67\x00")
        self._command(_UPDATE_2, b"\xd7")
        self._command(_ACTIVATE)
        time.sleep_ms(2)

    def clean(self, white=True):
        """Start a full refresh to all white (or black) with the controller's own waveform, and
        return without waiting for it (about 1.8 s).

        It flashes, but drives the glass harder than show(): black then white before show_grey()
        weakens what a long-held picture leaves showing through greys. The next show() is full.
        """
        self._restart()
        self._command(_BORDER, b"\x01")
        fill = 0xFF if white else 0x00
        self._converted_plane(_RAM_NEW, _fill, fill)
        self._converted_plane(_RAM_OLD, _fill, fill)
        self._command(_UPDATE_1, b"\x00")
        # Seeed_GFX2's and GxEPD2's full refresh: the OTP's full waveform, which then turns the
        # analog supply off itself.
        self._command(_UPDATE_2, b"\xf7")
        self._command(_ACTIVATE)
        time.sleep_ms(2)

    # Another waveform needs the controller reset first, as Seeed's driver does between modes: on
    # a unit, a second grey refresh without one swapped the two middle greys.
    def _restart(self):
        # Before the reset, which would cut a running refresh short. None runs after an init()
        # cut short, when BUSY may mean nothing.
        if not self._init_pending:
            self.wait()
        self._stale = True
        self.init()

    def power_off(self):
        """Turn the analog supply off after the refresh, keeping both planes for the next show().

        Returns without waiting for the power-down (about 140 ms), as show() does for a refresh.
        """
        # A second power-off with the supply already off leaves BUSY high until a reset.
        if self._powered is False:
            return
        self._wait_capped()
        # Unknown after a show() cut at 0x20: a reset turns it off whether it's on or not.
        if self._powered is None:
            self.init()
            return
        self._command(_BORDER, b"\x80")
        self._command(_UPDATE_2, b"\x03")
        self._command(_ACTIVATE)
        # Only once sent: cut short before this, the supply is still on and a retry is safe.
        self._powered = False
        time.sleep_ms(2)

    def sleep(self):
        """Power down and sleep, losing both planes. The next show() wakes it, and should be full."""
        if self._asleep:
            return
        self.power_off()
        self._wait_capped()
        # Set first: if cut short, the next show() resets an awake panel, which is harmless.
        self._asleep = True
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

    # A plane worked out a slice at a time, so no second frame-sized buffer is needed.
    def _converted_plane(self, cmd, convert, src, *args):
        self._home()
        buf = self._buf
        try:
            self._begin(cmd)
            for start in range(0, _PLANE, _SLICE):
                n = min(_SLICE, _PLANE - start)
                convert(buf, src, start, n, *args)
                self.spi.write(buf if n == _SLICE else memoryview(buf)[:n])
        finally:
            self.cs(1)
