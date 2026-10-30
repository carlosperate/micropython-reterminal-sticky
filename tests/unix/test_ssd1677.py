import asyncio
import unittest

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


class TestSSD1677(unittest.TestCase):
    def setUp(self):
        self.cs, self.dc, self.rst, self.busy = Pin(), Pin(), Pin(), Pin()
        self.spi = SPI(self.cs, self.dc)
        self.panel = ssd1677.SSD1677(self.spi, self.cs, self.dc, self.rst, self.busy)

    # A refresh turns the analog supply on, which power_off() and sleep() then turn off.
    def refreshed(self):
        self.panel.show(frame(1))
        del self.spi.log[:]

    def log(self):
        return [(cmd, bytes(data)) for cmd, data in self.spi.log]

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
            HOME + [(0x24, new)] + HOME + [(0x26, bytes(b ^ 0xFF for b in new))] + REFRESH,
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
