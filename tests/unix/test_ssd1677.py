import asyncio
import binascii
import unittest

import framebuf
import reterminal_sticky
import ssd1677
from fakes import SPI, Pin, script, word
from sticky.display import Display

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


def planes_as(new, old):
    return HOME + [(0x24, new)] + HOME + [(0x26, old)]


def frame(seed):
    return bytes((i * seed) & 0xFF for i in range(48000))


def inverse(plane):
    return bytes(b ^ 0xFF for b in plane)


# Fixtures only: the test classes share them without running each other's tests.
class PanelCase(unittest.TestCase):
    def setUp(self):
        self.cs, self.dc, self.rst, self.busy = Pin(), Pin(), Pin(), Pin()
        self.spi = SPI(self.cs, self.dc)
        # Initialised, as reterminal_sticky.panel() returns it.
        self.panel = self.new_panel()
        self.panel.init()
        del self.spi.log[:]

    # The Sticky's glass, with any setting replaced.
    def new_panel(self, **settings):
        glass = dict(reterminal_sticky._GLASS)
        glass.update(settings)
        return ssd1677.SSD1677(self.spi, self.cs, self.dc, self.rst, self.busy, **glass)

    def log(self):
        return [(cmd, bytes(data)) for cmd, data in self.spi.log]

    def plane(self, cmd):
        return [data for c, data in self.log() if c == cmd][-1]

    # Each plane's writes, by size, from here on.
    def slice_sizes(self):
        sizes = []
        write = self.spi.write

        def recording(buf):
            if self.dc.level:
                sizes[-1][1].append(len(buf))
            else:
                sizes.append((buf[0], []))
            write(buf)

        self.spi.write = recording
        return sizes


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
            planes_as(new, inverse(new)) + REFRESH,
        )

    # The first refresh is full whatever old is, so this is the second.
    def test_partial(self):
        self.refreshed()
        new, old = frame(3), frame(5)
        self.panel.show(new, old)
        self.assertEqual(self.log(), planes_as(new, old) + REFRESH)

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
        self.assertEqual(self.log(), POWER_OFF + [(0x10, b"\x03")])

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
        self.assertEqual(self.log(), POWER_OFF)
        # The planes stay, so the next refresh can be a partial: no reset or deep sleep.
        del self.spi.log[:]
        self.panel.show(frame(3), frame(5))
        self.assertEqual(self.log(), planes_as(frame(3), frame(5)) + REFRESH)

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

    # Cut as 0x20 goes out, the supply may be on or off, and 0x22 03 with it off would hold BUSY:
    # power_off() resets instead, which turns it off either way.
    def test_cut_at_activate_resets(self):
        write = self.spi.write

        def cut(buf):
            write(buf)
            if not self.dc.level and buf[0] == 0x20:
                raise KeyboardInterrupt

        self.spi.write = cut
        with self.assertRaises(KeyboardInterrupt):
            self.panel.show(frame(1))
        self.spi.write = write
        del self.spi.log[:]
        resets = []
        self.rst.on_change = resets.append
        self.panel.power_off()
        self.assertEqual((resets, self.log()), ([0, 1], []))
        # The controller needs init() again, and the next refresh is full.
        self.panel.show(frame(3), frame(1))
        self.assertEqual(self.log()[: len(INIT)], INIT)
        self.assertEqual(self.plane(0x26), inverse(frame(3)))

    # Cut as power-off's 0x20 goes out, the supply may be off already: the next one resets.
    def test_cut_power_off_resets(self):
        self.refreshed()
        write = self.spi.write

        def cut(buf):
            write(buf)
            if not self.dc.level and buf[0] == 0x20:
                raise KeyboardInterrupt

        self.spi.write = cut
        with self.assertRaises(KeyboardInterrupt):
            self.panel.power_off()
        self.spi.write = write
        del self.spi.log[:]
        resets = []
        self.rst.on_change = resets.append
        self.panel.power_off()
        self.assertEqual((resets, self.log()), ([0, 1], []))

    # Cut inside a reset, the supply may be off already: power_off() resets again.
    def test_cut_reset_leaves_supply_unknown(self):
        self.panel.show(frame(1))

        def cut(level):
            if level:
                raise KeyboardInterrupt

        self.rst.on_change = cut
        with self.assertRaises(KeyboardInterrupt):
            self.panel.clean()
        resets = []
        self.rst.on_change = resets.append
        del self.spi.log[:]
        self.panel.power_off()
        self.assertEqual((resets, self.log()), ([0, 1], []))

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

    # Converted planes go out in whole rows, each slice within one ESP32 SPI transaction.
    def test_slices(self):
        sizes = self.slice_sizes()
        self.panel.show(frame(1))
        self.panel.show_grey(grey_frame()[0])
        self.panel.clean()
        planes = [(cmd, data) for cmd, data in sizes if cmd in (0x24, 0x26)]
        sliced = [4000] * 12
        self.assertEqual(
            planes, [(0x24, [48000]), (0x26, sliced)] + [(0x24, sliced), (0x26, sliced)] * 2
        )

    # Programmes that never show greys don't hold the tables.
    def test_grey_tables_built_at_first_grey(self):
        self.panel.show(frame(1))
        self.assertIsNone(self.panel._tables)
        self.panel.show_grey(grey_frame()[0])
        self.assertIsNotNone(self.panel._tables)


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
            INIT + [(0x3C, b"\x00")] + planes_as(new, old) + GREY_REFRESH,
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
                INIT + [(0x3C, b"\x01")] + planes_as(plane, plane) + CLEAN_REFRESH,
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


# Built by hand and never initialised: the first refresh of any kind runs init(), once.
class TestFirstRefresh(PanelCase):
    def setUp(self):
        super().setUp()
        self.panel = self.new_panel()

    def test_show_initialises(self):
        new = frame(7)
        self.panel.show(new)
        self.assertEqual(self.log(), INIT + planes_as(new, inverse(new)) + REFRESH)

    # Nobody knows what the glass shows yet, so old is ignored.
    def test_first_show_is_full(self):
        new = frame(3)
        self.panel.show(new, frame(5))
        self.assertEqual(self.plane(0x26), inverse(new))

    def test_grey_and_clean_initialise_once(self):
        for call in (lambda: self.panel.show_grey(grey_frame()[0]), lambda: self.panel.clean()):
            self.panel = self.new_panel()
            del self.spi.log[:]
            call()
            self.assertEqual(self.log()[: len(INIT)], INIT)
            self.assertEqual(self.spi.commands().count(0x12), 1)

    def test_power_off_sends_nothing(self):
        self.panel.power_off()
        self.assertEqual(self.spi.log, [])

    def test_sleep_then_show_initialises(self):
        self.panel.sleep()
        del self.spi.log[:]
        self.panel.show(frame(1))
        self.assertEqual(self.log()[: len(INIT)], INIT)

    # As a controller an earlier driver put in deep sleep: BUSY high until a reset.
    def asleep_until_reset(self):
        self.busy.input = script([1])

        def wake(level):
            if level:
                self.busy.input = script([0])

        self.rst.on_change = wake
        self.panel.timeout_ms = 20

    def test_busy_counts_from_the_first_reset(self):
        self.asleep_until_reset()
        self.assertFalse(self.panel.busy())
        self.panel.wait()
        self.panel.show(frame(1))
        self.busy.input = script([1])
        self.assertTrue(self.panel.busy())

    # Display waits before it shows: that wait mustn't time out before the driver's init().
    def test_display_on_a_controller_left_asleep(self):
        self.asleep_until_reset()
        display = Display(self.panel)
        display.show()
        self.assertEqual(self.log()[: len(INIT)], INIT)
        self.assertFalse(self.panel._powered)


# Every byte the Sticky's settings send, planes as (length, CRC-32): init, a full and a partial
# refresh, power-off, grey, clean, a full refresh after it, and sleep.
STICKY_BYTES = (
    INIT
    + planes_as((48000, 230095691), (48000, 3809137738))
    + REFRESH
    + planes_as((48000, 113370961), (48000, 230095691))
    + REFRESH
    + POWER_OFF
    + INIT
    + [(0x3C, b"\x00")]
    + planes_as((48000, 3759742560), (48000, 2012162748))
    + GREY_REFRESH
    + INIT
    + [(0x3C, b"\x01")]
    + planes_as((48000, 178886727), (48000, 178886727))
    + CLEAN_REFRESH
    + planes_as((48000, 230095691), (48000, 3809137738))
    + REFRESH
    + POWER_OFF
    + [(0x10, b"\x03")]
)


class TestStickyBytes(PanelCase):
    def test_bytes(self):
        panel = self.panel
        panel.init()
        panel.show(frame(7))
        panel.show(frame(3), frame(7))
        panel.power_off()
        panel.show_grey(bytes((i * 5) & 0xFF for i in range(96000)))
        panel.clean(False)
        panel.show(frame(7), frame(3))
        panel.power_off()
        panel.sleep()
        log = [(c, d if len(d) <= 8 else (len(d), binascii.crc32(d))) for c, d in self.log()]
        self.assertEqual(log, STICKY_BYTES)


GREY = reterminal_sticky._GLASS["grey"]


class TestSettings(PanelCase):
    def small(self, **settings):
        return self.new_panel(width=400, height=300, **settings)

    # The last value each command was sent with.
    def sent(self):
        return dict(self.log())

    def test_size(self):
        self.assertEqual((self.panel.width, self.panel.height), (800, 480))
        panel = self.small()
        self.assertEqual((panel.width, panel.height), (400, 300))
        panel.init()
        self.assertEqual(self.sent()[0x01], word(299) + b"\x02")

    # 50 bytes a row: 81 rows fit a transaction, and the last slice is short.
    def test_small_slices(self):
        panel = self.small()
        sizes = self.slice_sizes()
        panel.show(bytes(15000))
        self.assertEqual([n for cmd, n in sizes if cmd == 0x26], [[4050, 4050, 4050, 2850]])

    def test_frame_sizes(self):
        panel = self.small()
        for call in (
            lambda: panel.show(frame(1)),
            lambda: panel.show(bytes(15000), frame(1)),
            lambda: panel.show_grey(bytes(96000)),
        ):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(self.spi.log, [])

    # Rows are whole bytes, and neither side is empty.
    def test_size_checked(self):
        for width, height in ((404, 480), (0, 480), (800, 0)):
            with self.assertRaises(ValueError):
                self.new_panel(width=width, height=height)

    def test_row_wider_than_transaction(self):
        panel = self.new_panel(width=32768, height=1)
        sizes = self.slice_sizes()
        panel.show(bytes(4096))
        self.assertEqual([n for cmd, n in sizes if cmd == 0x26], [[4096]])

    def test_settings_required(self):
        with self.assertRaises(TypeError):
            ssd1677.SSD1677(self.spi, self.cs, self.dc, self.rst, self.busy, 800, 480)

    # Bits 0 and 1 count X and Y up; a direction counting down starts at the far end.
    def test_data_entry(self):
        for mode, x, y in (
            (0x00, (399, 0), (299, 0)),
            (0x01, (0, 399), (299, 0)),
            (0x02, (399, 0), (0, 299)),
            (0x03, (0, 399), (0, 299)),
        ):
            del self.spi.log[:]
            self.small(data_entry=mode).init()
            sent = self.sent()
            self.assertEqual(sent[0x11], bytes((mode,)))
            self.assertEqual(
                (sent[0x44], sent[0x45]), (word(x[0]) + word(x[1]), word(y[0]) + word(y[1]))
            )
            self.assertEqual((sent[0x4E], sent[0x4F]), (word(x[0]), word(y[0])))

    # Bit 2 addresses along Y first, and frames go row by row.
    def test_data_entry_by_rows(self):
        with self.assertRaises(ValueError):
            self.new_panel(data_entry=0x05)

    # 0x1C runs a waveform without turning the clock and analog supply on; 0x01 never turns it off.
    def test_updates_checked(self):
        for settings in (
            {"refresh": (0xC0, 0x1C)},
            {"clean": (0x01, 0x1C)},
            {"grey": (0x00, 0x1C) + GREY[2:]},
            {"power_off": (0x80, 0x01)},
        ):
            with self.assertRaises(ValueError):
                self.new_panel(**settings)

    # The supply is off after init(); 0xFC leaves it on, so each refresh needs a power-off.
    def test_refresh_leaving_supply_on(self):
        self.panel.power_off()
        self.assertEqual(self.spi.log, [])
        for old in (None, frame(1)):
            self.panel.show(frame(3), old)
            del self.spi.log[:]
            self.panel.power_off()
            self.assertEqual(self.log(), POWER_OFF)

    def test_refresh_turning_supply_off(self):
        panel = self.new_panel(refresh=(0xC0, 0xFF))
        panel.show(frame(1))
        del self.spi.log[:]
        panel.power_off()
        self.assertEqual(self.spi.log, [])

    def test_no_grey(self):
        panel = self.new_panel(grey=None)
        with self.assertRaises(NotImplementedError):
            panel.show_grey(grey_frame()[0])
        self.assertEqual(self.spi.log, [])

    # A frame all at one level gives that level's bits in each plane; swapped levels swap them.
    def test_levels(self):
        levels = GREY[3]
        swapped = (levels[1], levels[0]) + levels[2:]
        for levels in (levels, swapped):
            panel = self.new_panel(grey=GREY[:3] + (levels,))
            for level in range(4):
                del self.spi.log[:]
                panel.show_grey(bytes((0x55 * level,)) * 96000)
                high, low = levels[level]
                self.assertEqual(self.plane(0x24), bytes((0xFF * high,)) * 48000)
                self.assertEqual(self.plane(0x26), bytes((0xFF * low,)) * 48000)
