import unittest

import reterminal_sticky
from fakes import I2C, Pin, Panel, script, word
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


class TestPower(unittest.TestCase):
    def test_gauge_scaled_for_r46(self):
        # The board's gauge reads ten times high: 7500 mAh for the 750 mAh cell.
        i2c = I2C({0x55: {0x0C: word(-300), 0x3C: word(7500)}})
        g = reterminal_sticky.gauge(i2c)
        self.assertEqual(g.current(), -30)
        self.assertEqual(g.design_capacity(), 750)

    def test_usb_power(self):
        self.assertTrue(reterminal_sticky.usb_power(Pin(1)))
        self.assertFalse(reterminal_sticky.usb_power(Pin(0)))

    def test_charging_is_stat_low_on_usb(self):
        self.assertTrue(reterminal_sticky.charging(Pin(0), Pin(1)))
        self.assertFalse(reterminal_sticky.charging(Pin(1), Pin(1)))

    def test_not_charging_off_usb(self):
        # Off USB a low STAT can only be the low half of a fault's blink.
        self.assertFalse(reterminal_sticky.charging(Pin(0), Pin(0)))

    def test_power_off(self):
        hold, lock, button, edges = Pin(1), Pin(1), Pin(), []  # latch set, as board_init.c does
        button.mode, button.input = Pin.IN, script([0, 0, 1])  # held, then released
        lock.on_change = lambda level: level and edges.append((hold(), button()))
        reterminal_sticky.power_off(hold, lock, button)
        # Cleared after the release; a fake board never loses power, as on USB, so set again.
        self.assertEqual(edges, [(0, 1), (1, 1)])

    def test_interrupted_power_off_sets_the_latch_again(self):
        hold, lock, button, edges = Pin(1), Pin(1), Pin(1), []  # the button already released

        # A Ctrl-C just after the latch is cleared, on USB.
        def edge(level):
            if level:
                edges.append(hold())
                if not hold():
                    raise KeyboardInterrupt

        lock.on_change = edge
        with self.assertRaises(KeyboardInterrupt):
            reterminal_sticky.power_off(hold, lock, button)
        self.assertEqual(edges, [0, 1])
