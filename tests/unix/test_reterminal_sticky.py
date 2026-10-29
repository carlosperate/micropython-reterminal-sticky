import unittest

import reterminal_sticky
from fakes import Pin, Panel
from reterminal_sticky import SSD1677, SSD2677


class TestReadId(unittest.TestCase):
    def test_reads_rev_on_sda(self):
        panel = Panel(reply=b"\x07\x01\x01")
        self.assertEqual(reterminal_sticky.read_id(panel.pins), b"\x07\x01\x01")
        self.assertEqual(panel.commands, [0x70])
        self.assertEqual(panel.powered_at_reset, [1])

    def test_leaves_bus_pins_outputs(self):
        panel = Panel(reply=b"\x07")
        reterminal_sticky.read_id(panel.pins)
        self.assertEqual(panel.cs.level, 1)
        self.assertEqual(panel.sda.mode, Pin.OUT)
        self.assertEqual(panel.sda.pull, None)

    def test_interrupted_read_releases_cs(self):
        panel = Panel(reply=b"\x07")

        def interrupted(level):
            if panel.dc.level:
                raise KeyboardInterrupt

        panel.sck.on_change = interrupted
        with self.assertRaises(KeyboardInterrupt):
            reterminal_sticky.read_id(panel.pins)
        self.assertEqual(panel.cs.level, 1)
        self.assertEqual(panel.sda.mode, Pin.OUT)

    def test_undriven_reads_ff(self):
        self.assertEqual(reterminal_sticky.read_id(Panel().pins, 1), b"\xff")


class TestDetect(unittest.TestCase):
    def detect(self, panel):
        return reterminal_sticky.detect(panel.pins)

    def test_ssd2677_by_rev(self):
        panel = Panel(reply=b"\x07\x01\x01", busy=(1,))
        self.assertEqual(self.detect(panel), SSD2677)
        self.assertEqual(panel.resets, 1)

    def test_other_rev_is_ssd1677(self):
        panel = Panel(reply=b"\x12", busy=(1,))
        self.assertEqual(self.detect(panel), SSD1677)
        self.assertEqual(panel.resets, 1)

    # The SSD2677 holds BUSY low for about 50 ms after a reset, then releases it.
    def test_undriven_busy_rises(self):
        panel = Panel(busy=(0,) * 20 + (1,))
        self.assertEqual(self.detect(panel), SSD2677)
        self.assertEqual(panel.resets, 2)

    def test_zero_busy_rises(self):
        panel = Panel(reply=b"\x00", busy=(0,) * 20 + (1,))
        self.assertEqual(self.detect(panel), SSD2677)

    def test_undriven_busy_falls(self):
        panel = Panel(busy=(1,) * 5 + (0,))
        self.assertEqual(self.detect(panel), SSD1677)

    def test_undriven_busy_stays_low(self):
        self.assertEqual(self.detect(Panel(busy=(0,))), SSD1677)

    def test_undriven_busy_stays_high(self):
        self.assertEqual(self.detect(Panel(busy=(1,))), SSD2677)
