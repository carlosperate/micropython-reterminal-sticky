# The bytes the SSD1677 driver sends with the Sticky's settings, read from its SPI writes: through
# the fakes on the unix port, to the real panel on the unit (whose glass shows the test patterns).
import binascii
import gc
import sys
import unittest

import reterminal_sticky
import ssd1677
from panel_log import (
    CLEAN_REFRESH,
    GREY_REFRESH,
    INIT,
    POWER_OFF,
    REFRESH,
    Recording,
    frame,
    grey_frame,
    inverse,
    leave_white,
    pattern,
    planes,
    planes_as,
)

BOARD = sys.platform == "esp32"
GLASS = reterminal_sticky._GLASS
if BOARD:
    from machine import Pin
else:
    sys.path.append("tests/unix")
    from fakes import SPI
    from fakes import Pin as FakePin


class BytesCase(unittest.TestCase):
    """A driver initialised, as panel() returns it, with its log empty."""

    def setUp(self):
        gc.collect()
        self.panel = self.new_panel()
        self.panel.init()
        del self.bus.log[:]

    def tearDown(self):
        if BOARD:
            self.panel.sleep()
        self.panel = self.bus = None

    @classmethod
    def tearDownClass(cls):
        leave_white()

    # Built by hand, never initialised. On the unit panel() powers the panel first.
    def new_panel(self):
        if BOARD:
            try:
                reterminal_sticky.panel().sleep()
            except NotImplementedError as e:
                self.skipTest(str(e))
            b = Pin.board
            pins = (b.EPD_CS, b.EPD_DC, b.EPD_RST, b.EPD_BUSY)
            panel = ssd1677.SSD1677(reterminal_sticky.spi(), *pins, **GLASS)
        else:
            cs, dc = FakePin(), FakePin()
            panel = ssd1677.SSD1677(SPI(cs, dc), cs, dc, FakePin(), FakePin(), **GLASS)
        self.bus = panel.spi = Recording(panel.spi, panel._cmd)
        return panel

    # Not copied: bytearray compares equal to bytes, and the unix port's heap is small.
    def log(self):
        return self.bus.log

    def plane(self, cmd):
        return [data for c, data in self.log() if c == cmd][-1]

    def commands(self):
        return [cmd for cmd, _ in self.bus.log]

    # A refresh turns the analog supply on, which power_off() and sleep() then turn off.
    def refreshed(self):
        self.panel.show(frame(1))
        del self.bus.log[:]

    # Each command's data writes, by size, from here on.
    def slice_sizes(self):
        sizes = []
        write = self.bus.write

        def recording(buf):
            if buf is self.bus.cmd:
                sizes.append((buf[0], []))
            else:
                sizes[-1][1].append(len(buf))
            write(buf)

        self.bus.write = recording
        return sizes


class TestRefresh(BytesCase):
    def test_init(self):
        self.panel.init()
        self.assertEqual(self.log(), INIT)

    def test_full(self):
        new = frame(7)
        self.panel.show(new)
        self.assertEqual(self.log(), planes_as(new, inverse(new)) + REFRESH)

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
        self.assertEqual(self.log(), [])

    def test_sleep(self):
        self.refreshed()
        self.panel.sleep()
        self.assertEqual(self.log(), POWER_OFF + [(0x10, b"\x03")])

    def test_power_off(self):
        self.refreshed()
        self.panel.power_off()
        self.assertEqual(self.log(), POWER_OFF)
        # The planes stay, so the next refresh can be a partial: no reset or deep sleep.
        del self.bus.log[:]
        self.panel.show(frame(3), frame(5))
        self.assertEqual(self.log(), planes_as(frame(3), frame(5)) + REFRESH)

    def test_sleep_twice(self):
        self.refreshed()
        self.panel.sleep()
        self.panel.sleep()
        self.assertEqual(self.commands(), [0x3C, 0x22, 0x20, 0x10])

    def test_sleep_without_refresh(self):
        self.panel.sleep()
        self.assertEqual(self.commands(), [0x10])

    # Converted planes go out in whole rows, each slice within one ESP32 SPI transaction.
    def test_slices(self):
        sizes = self.slice_sizes()
        self.panel.show(frame(1))
        self.panel.show_grey(grey_frame()[0])
        self.panel.clean()
        planes_sent = [(cmd, data) for cmd, data in sizes if cmd in (0x24, 0x26)]
        sliced = [4000] * 12
        self.assertEqual(
            planes_sent, [(0x24, [48000]), (0x26, sliced)] + [(0x24, sliced), (0x26, sliced)] * 2
        )

    # Programmes that never show greys don't hold the tables.
    def test_grey_tables_built_at_first_grey(self):
        self.panel.show(frame(1))
        self.assertIsNone(self.panel._tables)
        self.panel.show_grey(grey_frame()[0])
        self.assertIsNotNone(self.panel._tables)


class TestGreyBytes(BytesCase):
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
                del self.bus.log[:]
                self.panel.show_grey(buf)
                new, old = planes(fb, [(x, 5)])
                self.assertEqual(self.plane(0x24), new, (x, level))
                self.assertEqual(self.plane(0x26), old, (x, level))

    # Reset first: a second grey refresh without one swapped the middle greys on a unit.
    def test_sequence(self):
        buf, fb = pattern()
        self.panel.show_grey(buf)
        new, old = planes(fb)
        self.assertEqual(
            self.log(),
            INIT + [(0x3C, b"\x00")] + planes_as(new, old) + GREY_REFRESH,
        )

    def test_frame_size(self):
        for size in (48000, 95999):
            with self.assertRaises(ValueError):
                self.panel.show_grey(bytes(size))
        self.assertEqual(self.log(), [])

    # 0x22 D7 turns the supply off itself; a power-off after it hung BUSY on a unit.
    def test_no_power_off_after_grey(self):
        self.panel.show(frame(1))
        self.panel.show_grey(grey_frame()[0])
        del self.bus.log[:]
        self.panel.power_off()
        self.assertEqual(self.log(), [])
        self.panel.sleep()
        self.assertEqual(self.commands(), [0x10])

    # The OTP's full waveform to one colour, after a reset, as Seeed's and GxEPD2's full refresh.
    def test_clean(self):
        for white, fill in ((True, b"\xff"), (False, b"\x00")):
            del self.bus.log[:]
            self.panel.clean(white)
            plane = fill * 48000
            self.assertEqual(
                self.log(),
                INIT + [(0x3C, b"\x01")] + planes_as(plane, plane) + CLEAN_REFRESH,
            )


# Built by hand and never initialised: the first refresh of any kind runs init(), once.
class TestFirstRefreshBytes(BytesCase):
    def setUp(self):
        gc.collect()
        self.panel = self.new_panel()

    def test_show_initialises(self):
        new = frame(7)
        self.panel.show(new)
        self.assertEqual(self.log(), INIT + planes_as(new, inverse(new)) + REFRESH)

    def test_grey_and_clean_initialise_once(self):
        for call in (lambda: self.panel.show_grey(grey_frame()[0]), lambda: self.panel.clean()):
            self.panel = self.new_panel()
            call()
            self.assertEqual(self.log()[: len(INIT)], INIT)
            self.assertEqual(self.commands().count(0x12), 1)

    def test_power_off_sends_nothing(self):
        self.panel.power_off()
        self.assertEqual(self.log(), [])

    def test_sleep_then_show_initialises(self):
        self.panel.sleep()
        del self.bus.log[:]
        self.panel.show(frame(1))
        self.assertEqual(self.log()[: len(INIT)], INIT)


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


class TestStickyBytes(BytesCase):
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


if __name__ == "__main__":
    unittest.main()
