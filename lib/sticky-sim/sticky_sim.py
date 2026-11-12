# A panel driver's stand-in on the host: it keeps what the glass would show, counts refreshes and
# can write each one as a PBM (a grey one as a PGM). A package of its own, so nothing host-only
# sits in sticky.

import asyncio
import time

import micropython

WIDTH = 800
HEIGHT = 480
_PLANE = WIDTH * HEIGHT // 8
_GREY_FRAME = WIDTH * HEIGHT // 4
_GREYS = b"\x00\x55\xaa\xff"  # levels 0 to 3, as PGM values


# As the controller does: only pixels where old and new differ are driven.
@micropython.viper
def _refresh(glass: ptr8, new: ptr8, old: ptr8, n: int):
    for i in range(n):
        changed = new[i] ^ old[i]
        glass[i] = (glass[i] & (changed ^ 0xFF)) | (new[i] & changed)


@micropython.viper
def _invert(dst: ptr8, src: ptr8, n: int):
    for i in range(n):
        dst[i] = src[i] ^ 0xFF


# A grey frame in black and white: levels 2 and 3 white. GS2_HMSB's leftmost pixel is lowest.
@micropython.viper
def _threshold(dst: ptr8, src: ptr8, n: int):
    for i in range(n):
        pixels = src[2 * i] | (src[2 * i + 1] << 8)
        bits = 0
        for k in range(8):
            bits = (bits << 1) | ((pixels >> (2 * k + 1)) & 1)
        dst[i] = bits


class SimPanel:
    """The SSD1677 driver's interface. With path, each refresh is saved as path/00001.pbm on,
    a grey one as .pgm. glass is black and white; after show_grey(), greys holds the frame."""

    def __init__(self, path=None, refresh_ms=0, timeout_ms=10_000):
        self.path = path
        self.refresh_ms = refresh_ms
        self.timeout_ms = timeout_ms
        self.glass = bytearray(b"\xff" * _PLANE)
        self.full = 0
        self.partial = 0
        self.grey = 0
        self.cleaned = 0
        self.greys = None
        self.powered_off = 0
        self.powered = False
        self.asleep = False
        self._until = time.ticks_ms()
        self._old = bytearray(_PLANE)
        self._stale = False  # as the driver's: the next show() is full

    def init(self):
        self.asleep = False
        self.powered = False
        self._until = time.ticks_ms()

    def busy(self):
        return not self.asleep and time.ticks_diff(self._until, time.ticks_ms()) > 0

    def wait(self, timeout_ms=None):
        start = time.ticks_ms()
        while self.busy():
            self._check(start, timeout_ms)
            time.sleep_ms(1)

    async def wait_async(self, timeout_ms=None):
        start = time.ticks_ms()
        while self.busy():
            self._check(start, timeout_ms)
            await asyncio.sleep_ms(1)

    def _check(self, start, timeout_ms):
        if timeout_ms is None:
            timeout_ms = self.timeout_ms
        if time.ticks_diff(time.ticks_ms(), start) >= timeout_ms:
            raise OSError("busy timeout")

    def show(self, frame, old=None):
        if len(frame) != _PLANE or old is not None and len(old) != _PLANE:
            raise ValueError("frame size")
        if self.asleep:
            self.init()
        self.wait()
        if self._stale:
            old = None
        if old is None:
            _invert(self._old, frame, _PLANE)
            old = self._old
            self.full += 1
        else:
            self.partial += 1
        _refresh(self.glass, frame, old, _PLANE)
        self._stale = False
        self.greys = None
        self.powered = True
        self._until = time.ticks_add(time.ticks_ms(), self.refresh_ms)
        if self.path:
            self.save("%s/%05d.pbm" % (self.path, self.refreshes()))

    # As the driver does: the waveform turns the supply off.
    def show_grey(self, frame):
        if len(frame) != _GREY_FRAME:
            raise ValueError("frame size")
        self._restart()
        _threshold(self.glass, frame, _PLANE)
        self.greys = bytes(frame)
        self.grey += 1
        self._until = time.ticks_add(time.ticks_ms(), self.refresh_ms)
        if self.path:
            self.save_grey("%s/%05d.pgm" % (self.path, self.refreshes()))

    # As the driver does: a reset, then the glass all white or black; the next show() is full.
    def clean(self, white=True):
        self._restart()
        self.glass[:] = (b"\xff" if white else b"\x00") * _PLANE
        self.greys = None
        self.cleaned += 1
        self._until = time.ticks_add(time.ticks_ms(), self.refresh_ms)
        if self.path:
            self.save("%s/%05d.pbm" % (self.path, self.refreshes()))

    def refreshes(self):
        return self.full + self.partial + self.grey + self.cleaned

    # As the driver's: it waits before the reset, which would cut a refresh short.
    def _restart(self):
        self.wait()
        self._stale = True
        self.init()

    # As the driver does: only a supply a refresh turned on is turned off.
    def power_off(self):
        if not self.powered:
            return
        self._wait_capped()
        self.powered = False
        self.powered_off += 1

    def sleep(self):
        if self.asleep:
            return
        self.power_off()
        self._wait_capped()
        self.asleep = True

    # As the driver's 3 s cap, so power-off and sleep go ahead; a shorter timeout_ms cuts it.
    def _wait_capped(self):
        try:
            self.wait(min(self.timeout_ms, 3000))
        except OSError:
            pass

    def save(self, name):
        """Write the glass as a binary PBM, where 1 is black."""
        _invert(self._old, self.glass, _PLANE)
        with open(name, "wb") as f:
            f.write(b"P4\n800 480\n")
            f.write(self._old)

    def save_grey(self, name):
        """Write the last grey frame as a binary PGM."""
        row = bytearray(WIDTH)
        with open(name, "wb") as f:
            f.write(b"P5\n800 480\n255\n")
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    i = y * WIDTH + x
                    row[x] = _GREYS[(self.greys[i >> 2] >> ((i & 3) << 1)) & 3]
                f.write(row)
