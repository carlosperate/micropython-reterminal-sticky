# A panel driver's stand-in on the host: it keeps what the glass would show, counts refreshes and
# can write each one as a PBM. A package of its own, so nothing host-only sits in sticky.

import asyncio
import time

import micropython

WIDTH = 800
HEIGHT = 480
_PLANE = WIDTH * HEIGHT // 8


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


class SimPanel:
    """The SSD1677 driver's interface. With path, each refresh is saved as path/00001.pbm on."""

    def __init__(self, path=None, refresh_ms=0, timeout_ms=10_000):
        self.path = path
        self.refresh_ms = refresh_ms
        self.timeout_ms = timeout_ms
        self.glass = bytearray(b"\xff" * _PLANE)
        self.full = 0
        self.partial = 0
        self.powered_off = 0
        self.powered = False
        self.asleep = False
        self._until = time.ticks_ms()
        self._old = bytearray(_PLANE)

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
        if old is None:
            _invert(self._old, frame, _PLANE)
            old = self._old
            self.full += 1
        else:
            self.partial += 1
        _refresh(self.glass, frame, old, _PLANE)
        self.powered = True
        self._until = time.ticks_add(time.ticks_ms(), self.refresh_ms)
        if self.path:
            self.save("%s/%05d.pbm" % (self.path, self.full + self.partial))

    # As the driver does: only a supply a refresh turned on is turned off.
    def power_off(self):
        try:
            self.wait()
        except OSError:
            pass
        if self.powered and not self.asleep:
            self.powered = False
            self.powered_off += 1

    # As the driver does: it powers down even if the refresh never ends.
    def sleep(self):
        self.power_off()
        self.asleep = True

    def save(self, name):
        """Write the glass as a binary PBM, where 1 is black."""
        _invert(self._old, self.glass, _PLANE)
        with open(name, "wb") as f:
            f.write(b"P4\n800 480\n")
            f.write(self._old)
