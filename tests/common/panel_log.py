# The SSD1677's command log, for tests on the unix port and on the unit: Recording wraps the
# driver's SPI bus, and the sequences below are what the Sticky's settings send.
import sys

import framebuf
import reterminal_sticky

KINDS = ("full", "partial", "grey", "clean", "power_off")
_GLASS = reterminal_sticky._GLASS
# What each update sent with 0x22 starts, in the Sticky's settings.
_UPDATES = {
    _GLASS["refresh"][1]: "refresh",
    _GLASS["grey"][1]: "grey",
    _GLASS["clean"][1]: "clean",
    _GLASS["power_off"][1]: "power_off",
}


def counts(log):
    """{kind: n} for the updates in a log: a 0x20 starts the last 0x22's, and a black-and-white
    refresh is full when its old plane is the new one's inverse."""
    out = dict.fromkeys(KINDS, 0)
    new = old = update = None
    for cmd, data in log:
        if cmd == 0x24:
            new = data
        elif cmd == 0x26:
            old = data
        elif cmd == 0x22:
            update = data[0]
        elif cmd == 0x20:
            kind = _UPDATES[update]
            if kind == "refresh":
                full = all(o ^ n == 0xFF for o, n in zip(old, new))
                kind = "full" if full else "partial"
            out[kind] += 1
    return out


# On the unit, black then white: one full refresh to white still left test patterns ghosting.
def leave_white():
    if sys.platform != "esp32":
        return
    try:
        panel = reterminal_sticky.panel()
    except NotImplementedError:
        return
    panel.clean(False)
    panel.clean(True)
    panel.wait()
    panel.sleep()


class Recording:
    """The driver's SPI bus, logging (command, data): a command is written from its _cmd."""

    def __init__(self, spi, cmd, on_command=None):
        self.spi = spi
        self.cmd = cmd
        self.on_command = on_command
        self.log = []

    def write(self, buf):
        self.spi.write(buf)
        if buf is self.cmd:
            self.log.append((buf[0], bytearray()))
            if self.on_command:
                self.on_command(buf[0])
        elif self.log:
            self.log[-1][1].extend(buf)


# draftling's init for the Sticky's SSD1677.
INIT = [
    (0x12, b""),
    (0x18, b"\x80"),
    (0x0C, b"\xae\xc7\xc3\xc0\x80"),
    (0x01, b"\xdf\x01\x02"),
    (0x3C, b"\x80"),
    (0x11, b"\x01"),
    (0x44, b"\x00\x00\x1f\x03"),
    (0x45, b"\xdf\x01\x00\x00"),
    (0x4E, b"\x00\x00"),
    (0x4F, b"\xdf\x01"),
    (0x46, b"\xf7"),
    (0x47, b"\xf7"),
]
HOME = [(0x4E, b"\x00\x00"), (0x4F, b"\xdf\x01")]
REFRESH = [(0x21, b"\x00"), (0x3C, b"\xc0"), (0x22, b"\xfc"), (0x20, b"")]
CLEAN_REFRESH = [(0x21, b"\x00"), (0x22, b"\xf7"), (0x20, b"")]
POWER_OFF = [(0x3C, b"\x80"), (0x22, b"\x03"), (0x20, b"")]
GREY_REFRESH = [(0x21, b"\x00"), (0x1A, b"\x67\x00"), (0x22, b"\xd7"), (0x20, b"")]


def planes_as(new, old):
    return HOME + [(0x24, new)] + HOME + [(0x26, old)]


def frame(seed):
    return bytes((i * seed) & 0xFF for i in range(48000))


def inverse(plane):
    return bytes(b ^ 0xFF for b in plane)


def grey_frame(pixels=()):
    """A white GS2_HMSB frame with (x, y, level) set through framebuf, as programmes draw it."""
    buf = bytearray(96000)
    fb = framebuf.FrameBuffer(buf, 800, 480, framebuf.GS2_HMSB)
    fb.fill(3)
    for x, y, level in pixels:
        fb.pixel(x, y, level)
    return buf, fb


def pattern():
    # Every level at every position in a byte, varying along rows and down columns.
    buf, fb = grey_frame()
    for y in range(480):
        for x in range(800):
            fb.pixel(x, y, (x + y // 3 + x // 7) & 3)
    return buf, fb


def planes(fb, points=None):
    """The planes from fb.pixel() at points (every pixel by default; white elsewhere): 0x24 has a
    1 where the level is 0 or 1, 0x26 where 0 or 2."""
    new, old = bytearray(48000), bytearray(48000)
    a = framebuf.FrameBuffer(new, 800, 480, framebuf.MONO_HLSB)
    b = framebuf.FrameBuffer(old, 800, 480, framebuf.MONO_HLSB)
    for x, y in points or ((x, y) for y in range(480) for x in range(800)):
        level = fb.pixel(x, y)
        a.pixel(x, y, level <= 1)
        b.pixel(x, y, level in (0, 2))
    return bytes(new), bytes(old)
