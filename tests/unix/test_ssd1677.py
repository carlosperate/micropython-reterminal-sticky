import asyncio
import unittest

import framebuf
import ssd1677
from fakes import SPI, Pin, script

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


def frame(seed):
    return bytes((i * seed) & 0xFF for i in range(48000))


def inverse(plane):
    return bytes(b ^ 0xFF for b in plane)


# Fixtures only: the test classes share them without running each other's tests.
class PanelCase(unittest.TestCase):
    def setUp(self):
        self.cs, self.dc, self.rst, self.busy = Pin(), Pin(), Pin(), Pin()
        self.spi = SPI(self.cs, self.dc)
        self.panel = ssd1677.SSD1677(self.spi, self.cs, self.dc, self.rst, self.busy)

    def log(self):
        return [(cmd, bytes(data)) for cmd, data in self.spi.log]


class TestSSD1677(PanelCase):
    # A refresh turns the analog supply on, which power_off() and sleep() then turn off.
    def refreshed(self):
        self.panel.show(frame(1))
        del self.spi.log[:]

    def test_init(self):
        resets = []
        self.rst.on_change = resets.append
        self.panel.init()
        self.assertEqual(resets, [0, 1])
        self.assertEqual(self.log(), INIT)
        self.assertEqual(self.cs.level, 1)

    def test_full(self):
        new = frame(7)
        self.panel.show(new)
        self.assertEqual(
            self.log(),
            HOME + [(0x24, new)] + HOME + [(0x26, inverse(new))] + REFRESH,
        )

    def test_partial(self):
        new, old = frame(3), frame(5)
        self.panel.show(new, old)
        self.assertEqual(self.log(), HOME + [(0x24, new)] + HOME + [(0x26, old)] + REFRESH)

    def test_frame_size(self):
        with self.assertRaises(ValueError):
            self.panel.show(bytes(100))
        with self.assertRaises(ValueError):
            self.panel.show(frame(1), bytes(100))
        self.assertEqual(self.spi.log, [])

    def test_interrupted_write_releases_cs(self):
        def interrupted(buf):
            raise KeyboardInterrupt

        for old in (None, frame(5)):
            self.spi.write = interrupted
            with self.assertRaises(KeyboardInterrupt):
                self.panel.show(frame(3), old)
            self.assertEqual(self.cs.level, 1)

    def test_show_waits_for_busy(self):
        self.busy.input = script([1] * 5 + [0])
        self.panel.show(frame(1))
        self.assertFalse(self.panel.busy())

    def test_busy_timeout(self):
        self.busy.input = script([1])
        self.panel.timeout_ms = 20
        with self.assertRaises(OSError):
            self.panel.show(frame(1))
        self.assertEqual(self.spi.log, [])

    def test_wait_async(self):
        self.busy.input = script([1] * 3 + [0])
        asyncio.run(self.panel.wait_async())
        self.assertFalse(self.panel.busy())

    def test_sleep(self):
        self.refreshed()
        self.panel.sleep()
        self.assertEqual(
            self.log(), [(0x3C, b"\x80"), (0x22, b"\x03"), (0x20, b""), (0x10, b"\x03")]
        )

    # BUSY stays high in deep sleep; show() wakes the panel with init() first.
    def test_show_after_sleep(self):
        self.busy.input = script([0])
        self.panel.sleep()
        self.busy.input = script([1])
        self.assertFalse(self.panel.busy())
        self.panel.wait(0)
        del self.spi.log[:]
        self.busy.input = script([0])
        new = frame(7)
        self.panel.show(new)
        self.assertEqual(self.log()[: len(INIT)], INIT)
        self.assertEqual(self.log()[len(INIT) :][2], (0x24, new))

    def test_power_off(self):
        self.refreshed()
        self.panel.power_off()
        self.assertEqual(self.log(), [(0x3C, b"\x80"), (0x22, b"\x03"), (0x20, b"")])
        # The planes stay, so the next refresh can be a partial: no reset or deep sleep.
        del self.spi.log[:]
        self.panel.show(frame(3), frame(5))
        self.assertEqual(
            self.log(), HOME + [(0x24, frame(3))] + HOME + [(0x26, frame(5))] + REFRESH
        )

    def test_sleep_twice(self):
        self.refreshed()
        self.panel.sleep()
        self.panel.sleep()
        self.assertEqual(self.spi.commands(), [0x3C, 0x22, 0x20, 0x10])

    # On the unit a second power-off with the supply already off left BUSY high until a reset.
    def test_power_off_twice(self):
        self.refreshed()
        self.panel.power_off()
        self.panel.power_off()
        self.assertEqual(self.spi.commands(), [0x3C, 0x22, 0x20])

    # Cut short before the command is sent, the supply is still on: the next call sends it.
    def test_interrupted_power_off_retried(self):
        self.refreshed()
        write = self.spi.write

        def interrupted(buf):
            raise KeyboardInterrupt

        self.spi.write = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.panel.power_off()
        self.spi.write = write
        self.panel.power_off()
        self.assertEqual(self.spi.commands(), [0x3C, 0x22, 0x20])

    def test_sleep_without_refresh(self):
        self.panel.sleep()
        self.assertEqual(self.spi.commands(), [0x10])

    def test_wait_zero_doesnt_block(self):
        self.busy.input = script([1])
        with self.assertRaises(OSError):
            self.panel.wait(0)

    # draftling's power-off wait once hung; sleep goes on after 3 s.
    def test_sleep_while_busy(self):
        self.refreshed()
        self.busy.input = script([1])
        self.panel.sleep()
        self.assertEqual(self.spi.commands(), [0x3C, 0x22, 0x20, 0x10])

    def test_sleep_after_stuck_power_off(self):
        self.refreshed()
        self.busy.input = script([0, 1])
        self.panel.sleep()
        self.assertEqual(self.spi.commands()[-1], 0x10)


GREY_REFRESH = [(0x21, b"\x00"), (0x1A, b"\x67\x00"), (0x22, b"\xd7"), (0x20, b"")]


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


class TestGrey(PanelCase):
    def plane(self, cmd):
        return [data for c, data in self.log() if c == cmd][-1]

    # GS2_HMSB keeps the leftmost pixel in a byte's lowest two bits.
    def test_packing(self):
        buf, _ = grey_frame([(0, 0, 0), (1, 0, 1), (2, 0, 2), (3, 0, 3)])
        self.assertEqual(buf[0], 0xE4)
        self.panel.show_grey(buf)
        self.assertEqual(self.plane(0x24)[0], 0b11000000)
        self.assertEqual(self.plane(0x26)[0], 0b10100000)

    def test_planes_follow_pixels(self):
        buf, fb = pattern()
        self.panel.show_grey(buf)
        new, old = planes(fb)
        self.assertEqual(self.plane(0x24), new)
        self.assertEqual(self.plane(0x26), old)

    # Single pixels either side of a byte boundary, in both formats.
    def test_byte_boundaries(self):
        for x in (3, 4, 7, 8, 799):
            for level in range(3):
                buf, fb = grey_frame([(x, 5, level)])
                del self.spi.log[:]
                self.panel.show_grey(buf)
                new, old = planes(fb, [(x, 5)])
                self.assertEqual(self.plane(0x24), new, (x, level))
                self.assertEqual(self.plane(0x26), old, (x, level))

    # Reset first: a second grey refresh without one swapped the middle greys on a unit.
    def test_sequence(self):
        buf, fb = pattern()
        resets = []
        self.rst.on_change = resets.append
        self.panel.show_grey(buf)
        new, old = planes(fb)
        self.assertEqual(resets, [0, 1])
        self.assertEqual(
            self.log(),
            INIT + [(0x3C, b"\x00")] + HOME + [(0x24, new)] + HOME + [(0x26, old)] + GREY_REFRESH,
        )
        self.assertEqual(self.cs.level, 1)

    def test_frame_size(self):
        for size in (48000, 95999):
            with self.assertRaises(ValueError):
                self.panel.show_grey(bytes(size))
        self.assertEqual(self.spi.log, [])

    # A reset cuts a running refresh short, so the wait comes first.
    def test_waits_before_reset(self):
        for call in (lambda: self.panel.show_grey(grey_frame()[0]), self.panel.clean):
            events = []
            levels = script([1, 1, 0])

            def busy():
                level = levels()
                events.append(("busy", level))
                return level

            self.busy.input = busy
            self.rst.on_change = lambda level: events.append(("reset", level))
            call()
            self.assertTrue(events.index(("reset", 0)) > events.index(("busy", 0)))

    def test_full_after_grey(self):
        self.panel.show_grey(grey_frame()[0])
        new, old = frame(3), frame(5)
        del self.spi.log[:]
        self.panel.show(new, old)
        self.assertEqual(self.plane(0x26), inverse(new))
        # Once a full refresh has started, partials work again.
        self.panel.show(frame(7), new)
        self.assertEqual(self.plane(0x26), new)

    def interrupt(self, call, *args):
        write = self.spi.write

        def interrupted(buf):
            raise KeyboardInterrupt

        self.spi.write = interrupted
        with self.assertRaises(KeyboardInterrupt):
            call(*args)
        self.spi.write = write
        self.assertEqual(self.cs.level, 1)

    def test_interrupted_grey_leaves_next_full(self):
        self.panel.show(frame(1))
        self.interrupt(self.panel.show_grey, grey_frame()[0])
        new = frame(3)
        del self.spi.log[:]
        self.panel.show(new, frame(1))
        self.assertEqual(self.plane(0x26), inverse(new))

    def test_interrupted_full_after_grey_leaves_next_full(self):
        self.panel.show_grey(grey_frame()[0])
        self.interrupt(self.panel.show, frame(3), frame(5))
        new = frame(3)
        del self.spi.log[:]
        self.panel.show(new, frame(5))
        self.assertEqual(self.plane(0x26), inverse(new))

    # 0x22 D7 turns the supply off itself; a power-off after it hung BUSY on a unit.
    def test_no_power_off_after_grey(self):
        self.panel.show(frame(1))
        self.panel.show_grey(grey_frame()[0])
        del self.spi.log[:]
        self.panel.power_off()
        self.assertEqual(self.spi.log, [])
        self.panel.sleep()
        self.assertEqual(self.spi.commands(), [0x10])

    # A grey refresh that never starts changes nothing: the supply and the planes stay.
    def test_timeout_keeps_state(self):
        self.panel.show(frame(1))
        self.busy.input = script([1])
        self.panel.timeout_ms = 20
        del self.spi.log[:]
        with self.assertRaises(OSError):
            self.panel.show_grey(grey_frame()[0])
        self.assertEqual(self.spi.log, [])
        self.busy.input = script([0])
        self.panel.show(frame(3), frame(1))
        self.assertEqual(self.plane(0x26), frame(1))
        del self.spi.log[:]
        self.panel.power_off()
        self.assertEqual(self.spi.commands(), [0x3C, 0x22, 0x20])

    # A reset cut short (here at SWRESET) is done again before the next refresh of either kind.
    def test_cut_short_init_runs_again(self):
        for again in (
            lambda: self.panel.show(frame(1), frame(2)),
            lambda: self.panel.show_grey(grey_frame()[0]),
        ):
            self.interrupt(self.panel.show_grey, grey_frame()[0])
            del self.spi.log[:]
            self.panel.power_off()  # the reset turned the supply off
            self.assertEqual(self.spi.log, [])
            again()
            self.assertEqual(self.log()[: len(INIT)], INIT)

    # The OTP's full waveform to one colour, after a reset, as Seeed's and GxEPD2's full refresh.
    def test_clean(self):
        for white, fill in ((True, b"\xff"), (False, b"\x00")):
            del self.spi.log[:]
            self.panel.clean(white)
            plane = fill * 48000
            self.assertEqual(
                self.log(),
                INIT
                + [(0x3C, b"\x01")]
                + HOME
                + [(0x24, plane)]
                + HOME
                + [(0x26, plane)]
                + [(0x21, b"\x00"), (0x22, b"\xf7"), (0x20, b"")],
            )

    def test_clean_then_full_and_no_power_off(self):
        self.panel.show(frame(1))
        self.panel.clean()
        del self.spi.log[:]
        self.panel.power_off()  # 0x22 F7 turns the supply off itself
        self.assertEqual(self.spi.log, [])
        new = frame(3)
        self.panel.show(new, frame(1))
        self.assertEqual(self.plane(0x26), inverse(new))

    def test_grey_after_sleep(self):
        self.panel.sleep()
        self.busy.input = script([1])
        self.assertFalse(self.panel.busy())
        self.busy.input = script([0])
        del self.spi.log[:]
        self.panel.show_grey(grey_frame()[0])
        self.assertEqual(self.log()[: len(INIT)], INIT)
