import unittest

from bq27220 import BQ27220
from fakes import I2C, word


# Raw readings from a Sticky on battery at the REPL (2026-10-30).
RAW = {
    0x08: word(4193),
    0x0C: word(-300),
    0x10: word(7431),
    0x12: word(7500),
    0x14: word(-302),
    0x16: word(1476),
    0x2C: word(99),
    0x3C: word(7500),
}


def gauge(sense_mohm=10, changes={}):
    memory = dict(RAW)
    memory.update((register, word(value)) for register, value in changes.items())
    return BQ27220(I2C({0x55: memory}), sense_mohm=sense_mohm)


class TestBQ27220(unittest.TestCase):
    def test_unscaled_at_ti_calibration(self):
        g = gauge()
        self.assertEqual(g.voltage(), 4193)
        self.assertEqual(g.current(), -300)
        self.assertEqual(g.average_current(), -302)
        self.assertEqual(g.design_capacity(), 7500)

    def test_scaled_for_sense_resistor(self):
        g = gauge(sense_mohm=100)
        self.assertEqual(g.current(), -30)
        self.assertAlmostEqual(g.average_current(), -30.2)
        self.assertEqual(g.remaining_capacity(), 743)
        self.assertEqual(g.full_charge_capacity(), 750)
        self.assertEqual(g.design_capacity(), 750)

    def test_unscaled_readings(self):
        # Volts, a percentage and minutes don't depend on the sense resistor.
        g = gauge(sense_mohm=100)
        self.assertEqual(g.voltage(), 4193)
        self.assertEqual(g.charge(), 99)
        self.assertEqual(g.time_to_empty(), 1476)

    def test_charging_current_is_positive(self):
        # sticky-rs read 5702 while charging; the charger is set to 555 mA.
        self.assertAlmostEqual(gauge(100, {0x0C: 5702}).current(), 570.2)

    def test_time_to_empty_none_unless_discharging(self):
        self.assertIsNone(gauge(changes={0x16: 0xFFFF}).time_to_empty())

    def test_other_address(self):
        g = BQ27220(I2C({0x56: RAW}), addr=0x56)
        self.assertEqual(g.voltage(), 4193)
