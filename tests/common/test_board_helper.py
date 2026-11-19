# reterminal_sticky's sensor bus, gauge and display(): the unit's own, and on the unix port with a
# stand-in machine, the gauge's recorded registers and SimPanel in their place.
import sys
import unittest

import reterminal_sticky
from sticky.display import Display

BOARD = sys.platform == "esp32"
if not BOARD:
    sys.path.append("tests/unix")
    from fakes import GAUGE, I2C
    from sticky_sim import SimPanel


class TestI2C(unittest.TestCase):
    def setUp(self):
        reterminal_sticky._i2c = None
        if not BOARD:

            class machine:
                class I2C:
                    def __init__(self, id):
                        self.id = id

            self.saved = sys.modules.get("machine")
            sys.modules["machine"] = machine

    def tearDown(self):
        reterminal_sticky._i2c = None
        if not BOARD:
            sys.modules.pop("machine")
            if self.saved:
                sys.modules["machine"] = self.saved

    def test_built_once(self):
        self.assertIs(reterminal_sticky.i2c(), reterminal_sticky.i2c())

    def test_gauge_shares_it(self):
        first, second = reterminal_sticky.gauge(), reterminal_sticky.gauge()
        self.assertIs(first.i2c, second.i2c)
        self.assertIs(first.i2c, reterminal_sticky.i2c())

    def test_gauge_takes_a_bus(self):
        bus = object()
        self.assertIs(reterminal_sticky.gauge(bus).i2c, bus)
        self.assertIsNone(reterminal_sticky._i2c)


class TestGauge(unittest.TestCase):
    # Bounds that hold at any charge: the charger stops at 4.2 V and is set to 555 mA, so a scale
    # ten times out reads outside them.
    def test_plausible(self):
        gauge = reterminal_sticky.gauge(None if BOARD else I2C({0x55: GAUGE}))
        self.assertTrue(0 < gauge.voltage() <= 4400)
        self.assertTrue(0 <= gauge.state_of_charge() <= 100)
        self.assertTrue(-1000 <= gauge.current() <= 1000)
        # Seeed's 750 mAh cell: a gauge reset would bring back TI's 3000 mAh, and the wrong scale.
        self.assertEqual(gauge.design_capacity(), 750)


class TestDisplay(unittest.TestCase):
    def test_display_on_panel(self):
        if BOARD:
            try:
                display = reterminal_sticky.display()
            except NotImplementedError as e:
                self.skipTest(str(e))
            display.panel.sleep()
        else:
            panel, saved = SimPanel(), reterminal_sticky.panel
            reterminal_sticky.panel = lambda: panel
            try:
                display = reterminal_sticky.display()
            finally:
                reterminal_sticky.panel = saved
            self.assertIs(display.panel, panel)
        self.assertIsInstance(display, Display)
        self.assertEqual((display.width, display.height), (800, 480))


if __name__ == "__main__":
    unittest.main()
